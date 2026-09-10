"""L0 環境與記憶核心：不執行任務，只滲透進 L1–L5 的每一次決策。

三核：
  - 動態記憶引擎（STM / MTM / LTM）
  - 知識圖譜（規則實體 + 既有 VectorMemoryStore，不另開平行 Chroma）
  - 態勢感知雷達（backend.environment.global_monitor）

禁止新建 backend/knowledge/vector_store.py，以免與 backend/memory/vector_store.py 衝突。
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import (
    RahoLayer,
    l0_enabled,
    layer_label,
    raho_directory,
    raho_identity,
)
from backend.environment.global_monitor import EnvSnapshot
from backend.environment.global_monitor import snapshot as radar_snapshot
from backend.memory.context_compressor import compress, extract_decisions, summarize_trace
from backend.memory.entity_extractor import extract_entities

L0_MARKER = "[L0 環境與記憶核心]"
L0_LAYER = int(RahoLayer.L0_KERNEL)

KNOWLEDGE_SEED: tuple[dict[str, Any], ...] = (
    {
        "id": "term_conversion",
        "content": "轉化率：完成目標行為（下單／註冊）的訪客比例，須給出分子與分母。",
        "tags": ["電商", "轉化率", "KPI"],
    },
    {
        "id": "term_repurchase",
        "content": "復購率：既有用戶在週期內再次購買的比例，常用於促銷驗收。",
        "tags": ["電商", "復購"],
    },
    {
        "id": "guide_competitor",
        "content": "競爭對手監控合規指南：遵守 Robots 協議、強制頻率限制，禁止直連暴力爬蟲。",
        "tags": ["電商", "競品", "合規", "Robots", "爬蟲"],
    },
    {
        "id": "lesson_proxy",
        "content": "歷史教訓：直連爬蟲易被封鎖；成功解法是改走代理池 API 並限制頻率。",
        "tags": ["代理池", "反爬", "爬蟲"],
    },
    {
        "id": "pref_concise",
        "content": "部分用戶偏好簡潔報告、討厭大表格；Success Criteria 應限制字數。",
        "tags": ["簡潔", "表格", "偏好"],
    },
)


@dataclass
class KnowledgeEntity:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    relations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "metadata": dict(self.metadata),
            "relations": list(self.relations),
        }


@dataclass
class MemoryTrace:
    task_id: str
    layer: str
    node_id: str
    summary: str
    decisions: list[str] = field(default_factory=list)
    failure_reason: str = ""
    horizon: str = "mtm"  # stm | mtm | ltm

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "layer": self.layer,
            "node_id": self.node_id,
            "summary": self.summary,
            "decisions": list(self.decisions),
            "failure_reason": self.failure_reason,
            "horizon": self.horizon,
        }


def _store():
    from backend.company.raho.store import STORE

    return STORE


def remember_query(query: str, *, task_id: str = "") -> list[KnowledgeEntity]:
    """從用戶／門票文字抽出實體，寫入 L0 知識倉（記憶體，重啟即清空）。"""
    store = _store()
    hits = match_knowledge(query)
    for entity in hits:
        store.l0_entities[entity.id] = entity.to_dict()
    terms = extract_entities(query)
    if terms:
        store.l0_prefs.setdefault("last_entities", "、".join(terms))
        if any(t in {"簡潔", "討厭表格", "不要表格"} for t in terms) or "簡潔" in (query or ""):
            store.l0_prefs["style"] = "concise"
    if query.strip():
        record_trace(
            task_id=task_id or "query",
            layer="L5",
            node_id="",
            summary=compress(query, 180),
            decisions=extract_decisions(query),
            horizon="stm",
        )
    return hits


def record_trace(
    *,
    task_id: str,
    layer: str,
    node_id: str = "",
    summary: str,
    decisions: list[str] | None = None,
    failure_reason: str = "",
    horizon: str = "mtm",
) -> dict[str, Any]:
    store = _store()
    row = MemoryTrace(
        task_id=task_id,
        layer=layer,
        node_id=node_id or uuid.uuid4().hex[:8],
        summary=compress(summary, 280),
        decisions=list(decisions or []),
        failure_reason=compress(failure_reason, 160),
        horizon=horizon,
    ).to_dict()
    store.l0_traces.append(row)
    while len(store.l0_traces) > 80:
        store.l0_traces.pop(0)
    return row


def match_knowledge(query: str, *, use_vector: bool = False) -> list[KnowledgeEntity]:
    terms = {t.lower() for t in extract_entities(query)}
    blob = (query or "").lower()
    hits: list[KnowledgeEntity] = []
    seen: set[str] = set()
    for seed in KNOWLEDGE_SEED:
        tags = [str(t) for t in seed.get("tags") or []]
        if terms & {t.lower() for t in tags} or any(t.lower() in blob for t in tags):
            if seed["id"] in seen:
                continue
            seen.add(seed["id"])
            hits.append(
                KnowledgeEntity(
                    id=str(seed["id"]),
                    content=str(seed["content"]),
                    metadata={"source": "seed", "tags": tags, "version": 1},
                    relations=[t for t in tags if t.lower() in blob or t.lower() in terms],
                )
            )
    store = _store()
    for raw in store.l0_entities.values():
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get("id") or "")
        if not eid or eid in seen:
            continue
        tags = list((raw.get("metadata") or {}).get("tags") or [])
        content = str(raw.get("content") or "")
        if terms & {str(t).lower() for t in tags} or any(str(t).lower() in blob for t in tags):
            seen.add(eid)
            hits.append(
                KnowledgeEntity(
                    id=eid,
                    content=content,
                    metadata=dict(raw.get("metadata") or {}),
                    relations=list(raw.get("relations") or []),
                )
            )
    if hits:
        return hits[:6]
    # 預設不碰 Chroma，避免 Prompt 組裝被嵌入／連線拖死（測試與離線）
    return _vector_hits(query) if use_vector else []


def _vector_hits(query: str) -> list[KnowledgeEntity]:
    if not (query or "").strip():
        return []
    try:
        from backend.memory.vector_store import VectorMemoryStore

        store = VectorMemoryStore()
        rows = store.search_similar(query, k=3) or []
    except Exception:
        return []
    out: list[KnowledgeEntity] = []
    for i, row in enumerate(rows):
        text = str(row.get("text") or "")
        if not text:
            continue
        out.append(
            KnowledgeEntity(
                id=str((row.get("metadata") or {}).get("id") or f"vec-{i}"),
                content=compress(text, 240),
                metadata={"source": "chroma", **dict(row.get("metadata") or {})},
                relations=[],
            )
        )
    return out


def traces_from_trees(query: str = "") -> list[MemoryTrace]:
    """從質詢樹衍生 STM／MTM，與角色名冊共用同一棵樹。"""
    store = _store()
    out: list[MemoryTrace] = []
    needle = (query or "").strip().lower()
    for tree in store.list_trees():
        goal = str(getattr(tree, "goal", "") or "")
        if needle and needle not in goal.lower() and needle not in (tree.run_id or "").lower():
            if not any(needle in str(getattr(n, "summary", "")).lower() for n in tree.nodes):
                continue
        for node in tree.nodes[-12:]:
            kind = str(getattr(node, "kind", "") or "")
            summary = str(getattr(node, "summary", "") or "")
            horizon = "stm" if getattr(node, "status", "") in {"open", "blocked"} else "mtm"
            failure = summary if kind in {"mgp", "inspect", "rework", "escalate"} else ""
            out.append(
                MemoryTrace(
                    task_id=tree.run_id,
                    layer=f"L{getattr(node, 'from_layer', 2)}",
                    node_id=str(getattr(node, "node_id", "")),
                    summary=summarize_trace(title=kind, body=summary, failure_reason=failure),
                    decisions=extract_decisions(summary),
                    failure_reason=failure,
                    horizon=horizon,
                )
            )
    out.extend(_trace_from_dict(row) for row in store.l0_traces[-20:] if isinstance(row, dict))
    return out[-24:]


def _trace_from_dict(row: dict[str, Any]) -> MemoryTrace:
    return MemoryTrace(
        task_id=str(row.get("task_id") or ""),
        layer=str(row.get("layer") or "L0"),
        node_id=str(row.get("node_id") or ""),
        summary=str(row.get("summary") or ""),
        decisions=list(row.get("decisions") or []),
        failure_reason=str(row.get("failure_reason") or ""),
        horizon=str(row.get("horizon") or "mtm"),
    )


def long_term_hints(query: str) -> list[str]:
    # 不呼叫角色向量庫：組裝 Prompt 時必須零外部 IO。
    store = _store()
    hints: list[str] = []
    if store.l0_prefs.get("style") == "concise" or "簡潔" in (query or ""):
        hints.append("該用戶偏好簡潔輸出：每個 L2 Success Criteria 應限制字數（例如不得超過 500 字）。")
    lessons = [
        t
        for t in traces_from_trees(query)
        if t.failure_reason and t.horizon in {"mtm", "ltm"}
    ]
    for lesson in lessons[:3]:
        hints.append(f"歷史教訓：{lesson.summary}")
    return hints[:5]


def brief_for(layer: int, query: str, *, task_id: str = "") -> str:
    """組裝要塞進 System Prompt 頭部的 L0 片段。"""
    if not l0_enabled():
        return ""
    env = radar_snapshot()
    knowledge = match_knowledge(query)
    hints = long_term_hints(query)
    traces = [t for t in traces_from_trees(query) if t.horizon in {"stm", "mtm"}][:3]
    lines = [L0_MARKER, f"層級：{layer_label(layer)}"]
    if task_id:
        lines.append(f"任務：{task_id}")
    lines.append(f"態勢雷達：{env.bias_instructions}")
    if knowledge:
        lines.append("知識庫：")
        lines.extend(f"- {item.content}" for item in knowledge[:3])
    if hints:
        lines.append("長期記憶：")
        lines.extend(f"- {h}" for h in hints[:3])
    if traces:
        lines.append("近期軌跡：")
        lines.extend(f"- {t.summary}" for t in traces[:3])
    if int(layer) == int(RahoLayer.L4_AUDITOR):
        lines.append("L4：先引用知識庫定義再追問，禁止雙方對基礎名詞各說各話。")
    elif int(layer) == int(RahoLayer.L3_COMMANDER):
        lines.append("L3：拆解前套用歷史成功結構與用戶偏好；環境吃緊時降低 Max Iterations。")
    elif int(layer) == int(RahoLayer.L2_EXECUTOR):
        lines.append("L2：戰前檢查須引用知識庫合規條款；節能模式下 Max Iterations 視為 1，禁止幻想成功。")
    elif int(layer) == int(RahoLayer.L1_INSPECTOR):
        lines.append("L1：結構／事實失敗不得降級；僅邊界項且節能模式可 CONDITIONAL_PASS。")
    return compress("\n".join(lines), 900)


def inject_l0(system_prompt: str, layer: int, query: str = "", *, task_id: str = "") -> str:
    body = (system_prompt or "").strip()
    if not l0_enabled() or L0_MARKER in body:
        return body
    fragment = brief_for(layer, query, task_id=task_id)
    if not fragment:
        return body
    return f"{fragment}\n\n{body}".strip()


def apply_radar_bias(verdict: Any, env: EnvSnapshot | None = None) -> Any:
    """L1 節能：僅邊界檢驗失敗且分數夠高時降級通過。結構／事實失敗一律不放。"""
    if verdict is None or not l0_enabled():
        return verdict
    env = env or radar_snapshot()
    if not env.energy_save:
        return verdict
    from backend.company.raho.inspector import (
        TEST_EDGE,
        TEST_FACTUAL,
        TEST_SCHEMA,
        VERDICT_APPROVED,
        VERDICT_REWORK,
    )

    if getattr(verdict, "verdict", "") != VERDICT_REWORK:
        return verdict
    grill = getattr(verdict, "grill", None)
    failed = str(getattr(grill, "failed_test", "") or "")
    if failed in {TEST_SCHEMA, TEST_FACTUAL}:
        return verdict
    if float(getattr(verdict, "quality_score", 0) or 0) < 80:
        return verdict
    if failed and failed != TEST_EDGE:
        return verdict
    verdict.verdict = VERDICT_APPROVED
    verdict.details = f"{verdict.details or ''}｜L0 降級通過：{env.bias_instructions}".strip("｜")
    tests = dict(getattr(verdict, "test_results", None) or {})
    if tests.get("edge_case") == "FAIL":
        tests["edge_case"] = "PASS (L0 conditional)"
        verdict.test_results = tests
    return verdict


def attach_to_plan(pack: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    """把 L0 快照掛到 L3 作戰包；節能時只加註，不改測試依賴的預設迭代。"""
    if not isinstance(pack, dict) or not l0_enabled():
        return pack
    snap = kernel_snapshot(query=query)
    pack["l0"] = snap
    env = snap.get("radar") or {}
    if env.get("energy_save"):
        plan = pack.get("battle_plan")
        if isinstance(plan, dict):
            for inst in plan.get("atomic_role_instances") or []:
                if isinstance(inst, dict):
                    inst["l0_bias"] = env.get("bias_instructions") or ""
                    if "max_iterations" in inst:
                        try:
                            inst["max_iterations"] = min(int(inst["max_iterations"]), 1)
                        except (TypeError, ValueError):
                            pass
    if snap.get("prefs", {}).get("style") == "concise":
        plan = pack.get("battle_plan")
        if isinstance(plan, dict):
            for inst in plan.get("atomic_role_instances") or []:
                if isinstance(inst, dict) and "success_criteria" in inst:
                    criteria = str(inst.get("success_criteria") or "")
                    if "500 字" not in criteria and "字數" not in criteria:
                        inst["success_criteria"] = f"{criteria}；字數不得超過 500 字".strip("；")
    return pack


def kernel_snapshot(*, query: str = "", node_id: str = "") -> dict[str, Any]:
    env = radar_snapshot()
    if query:
        knowledge = match_knowledge(query)
    else:
        knowledge = [
            KnowledgeEntity(
                id=str(row.get("id") or ""),
                content=str(row.get("content") or ""),
                metadata=dict(row.get("metadata") or {}),
                relations=list(row.get("relations") or []),
            )
            for row in list(_store().l0_entities.values())[:8]
            if isinstance(row, dict)
        ]
        if not knowledge:
            knowledge = [
                KnowledgeEntity(
                    id=str(seed["id"]),
                    content=str(seed["content"]),
                    metadata={"source": "seed", "tags": list(seed["tags"])},
                )
                for seed in KNOWLEDGE_SEED[:3]
            ]
    traces = traces_from_trees(query)
    if node_id:
        traces = [t for t in traces if t.node_id == node_id] or traces
    ident = raho_identity("environment_kernel")
    return {
        "layer": ident["layer"],
        "id": "l0_kernel",
        "role_id": ident["role_id"],
        "label": ident["full"],
        "short": ident["short"],
        "spine": ident["spine"],
        "grill_targets": ident["grill_targets"],
        "enabled": l0_enabled(),
        "query": query,
        "radar": env.to_dict(),
        "knowledge": [k.to_dict() for k in knowledge[:8]],
        "traces": [t.to_dict() for t in traces[:16]],
        "prefs": dict(_store().l0_prefs),
        "directory": raho_directory(),
        "generated_at": time.time(),
    }


def l0_flag() -> bool:
    return os.getenv("EVOL_RAHO_L0", "true").lower() in {"1", "true", "yes", "on"}
