"""Token 節省上下文編排器。

核心思想（對齊 TODO §5「降 LLM 依賴」與 C-LLM-002 原因碼契約）：
組 prompt 時，**不**把完整對話歷史塞進上下文，而是依序向已啟用的
整合層召回「最小可用片段」：

1. **MemOS**：長期記憶（使用者偏好、過往結論）
2. **OpenViking**：L0 摘要 → 高分項才升 L1 概覽（分層載入）
3. **WeKnora**：知識庫 top-k 段落（帶 knowledge_id 可引用）

每個來源 fail-open：不可用就跳過並記原因碼，絕不阻斷生成。
所有片段經 L0 注入前脱敏（C-L0-002 ``redact``）後才進 prompt。

歷史壓縮策略：``assemble`` 回傳 ``history_window``（只保留最近 N 輪原文），
其餘由召回片段承載；``token_report`` 給出估算的節省量，供 §3 可視化展示。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.company.raho.l0_pipeline import redact
from backend.core.decision_router import REASON_CACHE_HIT
from backend.core.typed_llm_cache import CacheKind, TypedLLMCache
from backend.integrations.memos import MemosClient
from backend.integrations.openviking import OpenVikingClient
from backend.integrations.weknora import WeKnoraClient

logger = logging.getLogger(__name__)

# 粗略 token 估算（中英混合，約 1 token ≈ 2 字元）
CHARS_PER_TOKEN = 2

REASON_RECALL_ASSEMBLED = "recall_assembled"
REASON_ALL_SOURCES_DEGRADED = "recall_all_degraded"


@dataclass(frozen=True)
class RecallPolicy:
    """召回預算與視窗策略（可配置）。"""

    history_window: int = 6          # 只保留最近 N 輪原文
    memos_top_k: int = 5
    memos_max_chars: int = 1200
    viking_top_k: int = 5
    viking_max_chars: int = 2000
    weknora_top_k: int = 5
    weknora_max_chars: int = 1500
    cache_recall: bool = True        # 召回結果走 REFLECTION 類快取（審計路徑仍旁路）


@dataclass
class AssembledContext:
    """編排結果：注入片段＋截斷後歷史＋可觀測報告。"""

    fragments: list[dict[str, str]] = field(default_factory=list)  # [{source, text}]
    history: list[dict[str, str]] = field(default_factory=list)    # 截斷後的原文輪次
    reason_codes: list[str] = field(default_factory=list)
    degraded_sources: list[str] = field(default_factory=list)
    token_report: dict[str, int] = field(default_factory=dict)

    def render_injection(self) -> str:
        """渲染為可直接放入 system/context 的注入文本。"""
        lines: list[str] = []
        for frag in self.fragments:
            lines.append(f"[{frag['source']}] {frag['text']}")
        return "\n".join(lines)


@dataclass
class ContextAssembler:
    """召回編排器：記憶（MemOS）＋分層上下文（OpenViking）＋知識（WeKnora）。"""

    memos: MemosClient | None = None
    viking: OpenVikingClient | None = None
    weknora: WeKnoraClient | None = None
    cache: TypedLLMCache = field(default_factory=TypedLLMCache)
    policy: RecallPolicy = field(default_factory=RecallPolicy)

    def assemble(
        self,
        query: str,
        history: list[dict[str, str]],
        *,
        user_id: str = "default",
        cube_ids: list[str] | None = None,
        knowledge_base_id: str = "",
        audit_path: bool = False,
    ) -> AssembledContext:
        """組裝最小上下文。``audit_path=True`` 時召回快取旁路（C-LLM-003）。"""
        out = AssembledContext()
        p = self.policy

        # 1) 歷史截斷：只留最近 N 輪，其餘交給召回
        kept = history[-p.history_window :] if p.history_window > 0 else []
        out.history = list(kept)
        dropped = max(0, len(history) - len(kept))

        # 2) 依序召回（全部 fail-open）
        self._recall_memos(query, user_id=user_id, cube_ids=cube_ids or [], out=out, audit_path=audit_path)
        self._recall_viking(query, out=out)
        self._recall_weknora(query, knowledge_base_id=knowledge_base_id, out=out)

        if not out.fragments and out.degraded_sources:
            out.reason_codes.append(REASON_ALL_SOURCES_DEGRADED)
        else:
            out.reason_codes.append(REASON_RECALL_ASSEMBLED)

        # 3) token 節省報告（估算值，供監控面板展示）
        injected_chars = sum(len(f["text"]) for f in out.fragments)
        kept_chars = sum(len(m.get("content", "")) for m in out.history)
        dropped_chars = sum(len(m.get("content", "")) for m in history[:dropped]) if dropped else 0
        out.token_report = {
            "history_dropped_turns": dropped,
            "history_est_tokens": (kept_chars + dropped_chars) // CHARS_PER_TOKEN,
            "kept_est_tokens": kept_chars // CHARS_PER_TOKEN,
            "recall_est_tokens": injected_chars // CHARS_PER_TOKEN,
            "est_saved_tokens": max(0, dropped_chars - injected_chars) // CHARS_PER_TOKEN,
        }
        return out

    # ── 內部：三來源召回（片段一律先脱敏再注入，C-L0-002）──

    def _recall_memos(self, query: str, *, user_id: str, cube_ids: list[str], out: AssembledContext, audit_path: bool) -> None:
        if self.memos is None or not self.memos.http.enabled or not cube_ids:
            return
        cache_key = f"memos:{user_id}:{query}"
        if self.policy.cache_recall and not audit_path:
            hit = self.cache.get(CacheKind.REFLECTION, cache_key)
            if hit.hit and hit.value:
                out.fragments.append({"source": "memos", "text": hit.value})
                out.reason_codes.append(REASON_CACHE_HIT)
                return
        result = self.memos.recall_for_prompt(
            query, user_id=user_id, cube_ids=cube_ids, top_k=self.policy.memos_top_k, max_chars=self.policy.memos_max_chars
        )
        if result["degraded"]:
            out.degraded_sources.append("memos")
            out.reason_codes.append(result["reason_code"])
            return
        for text in result["fragments"]:
            clean, _ = redact(text)
            if clean.strip():
                out.fragments.append({"source": "memos", "text": clean})
        joined = "\n".join(f["text"] for f in out.fragments if f["source"] == "memos")
        if joined and self.policy.cache_recall and not audit_path:
            self.cache.put(CacheKind.REFLECTION, cache_key, joined)

    def _recall_viking(self, query: str, *, out: AssembledContext) -> None:
        if self.viking is None or not self.viking.http.enabled:
            return
        result = self.viking.recall_tiered(query, top_k=self.policy.viking_top_k, max_chars=self.policy.viking_max_chars)
        if result["degraded"]:
            out.degraded_sources.append("openviking")
            out.reason_codes.append(result["reason_code"])
            return
        for frag in result["fragments"]:
            clean, _ = redact(frag["text"])
            if clean.strip():
                out.fragments.append({"source": f"openviking:{frag['tier']}", "text": clean})

    def _recall_weknora(self, query: str, *, knowledge_base_id: str, out: AssembledContext) -> None:
        if self.weknora is None or not self.weknora.http.enabled:
            return
        result = self.weknora.recall_passages(
            query, knowledge_base_id=knowledge_base_id, top_k=self.policy.weknora_top_k, max_chars=self.policy.weknora_max_chars
        )
        if result["degraded"]:
            out.degraded_sources.append("weknora")
            out.reason_codes.append(result["reason_code"])
            return
        for frag in result["fragments"]:
            clean, _ = redact(frag["text"])
            if clean.strip():
                kid = frag.get("knowledge_id") or ""
                label = f"weknora:{kid}" if kid else "weknora"
                out.fragments.append({"source": label, "text": clean})
