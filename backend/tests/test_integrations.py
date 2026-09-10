"""外部整合層測試（MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil）。

全部經假 transport 隔離，不依賴真實服務（AGENTS.md 約束 #2）。
契約重點：fail-open、顯式啟用、原因碼可觀測、審計軌跡、注入前脱敏。
"""

from __future__ import annotations

import json

import pytest

from backend.integrations.base import (
    ERR_INTEGRATION_DISABLED,
    ERR_INTEGRATION_UNREACHABLE,
    IntegrationConfig,
    ResilientHttpClient,
)
from backend.integrations.context_assembler import ContextAssembler, RecallPolicy
from backend.integrations.memos import MemosClient
from backend.integrations.openpencil import OpenPencilClient
from backend.integrations.openviking import OpenVikingClient, VikingTier
from backend.integrations.ouroboros import (
    AMBIGUITY_GATE,
    ERR_AMBIGUITY_GATE_BLOCKED,
    OuroborosClient,
)
from backend.integrations.weknora import WeKnoraClient
from backend.integrations.yao import YaoClient


def _cfg(name: str, enabled: bool = True) -> IntegrationConfig:
    return IntegrationConfig(name=name, base_url="http://fake.local", enabled=enabled)


def _transport_ok(payload: dict | list | None = None):
    def _t(method, url, headers, body, timeout):
        return 200, json.dumps(payload if payload is not None else {"ok": True}).encode()

    return _t


def _transport_down(method, url, headers, body, timeout):
    raise TimeoutError("connection refused")


# ═══════════════════════════════════════════════════════════════
# 基底：fail-open 與審計軌跡
# ═══════════════════════════════════════════════════════════════

def test_base_disabled_is_fail_closed_without_network():
    """未顯式啟用 → 不發任何請求，回 ERR_INTEGRATION_DISABLED。"""
    called: list = []
    client = ResilientHttpClient(_cfg("memos", enabled=False), transport=lambda *a: called.append(a) or (200, b"{}"))
    resp = client.post("product/search", {"query": "x"})
    assert resp.ok is False and resp.error_code == ERR_INTEGRATION_DISABLED
    assert called == []


def test_base_unreachable_fails_open_with_reason_code():
    client = ResilientHttpClient(_cfg("weknora"), transport=_transport_down)
    resp = client.post("api/v1/knowledge-search", {"query": "x"})
    assert resp.ok is False and resp.error_code == ERR_INTEGRATION_UNREACHABLE
    assert resp.reason_code == "integration:weknora:unreachable"


def test_base_writes_audit_trail_per_call():
    events: list[dict] = []
    client = ResilientHttpClient(_cfg("yao"), transport=_transport_ok(), trail=events.append)
    client.get("api/v1/workspaces")
    client.get("api/v1/workspaces")
    assert len(events) == 2
    assert all(e["type"] == "integration_call" and e["integration"] == "yao" for e in events)
    assert all(e["ok"] is True for e in events)


# ═══════════════════════════════════════════════════════════════
# MemOS：召回取代完整歷史
# ═══════════════════════════════════════════════════════════════

def test_memos_recall_truncates_to_budget():
    payload = {"data": {"memories": [{"memory": "甲" * 800}, {"memory": "乙" * 800}]}}
    memos = MemosClient(config=_cfg("memos"), transport=_transport_ok(payload))
    out = memos.recall_for_prompt("偏好", user_id="u1", cube_ids=["c1"], max_chars=1000)
    assert out["degraded"] is False
    assert sum(len(f) for f in out["fragments"]) <= 1000


def test_memos_degraded_returns_empty_not_exception():
    memos = MemosClient(config=_cfg("memos"), transport=_transport_down)
    out = memos.recall_for_prompt("q", user_id="u1", cube_ids=["c1"])
    assert out["degraded"] is True and out["fragments"] == []
    assert out["reason_code"] == "integration:memos:unreachable"


# ═══════════════════════════════════════════════════════════════
# OpenViking：L0/L1 分層載入
# ═══════════════════════════════════════════════════════════════

def test_openviking_tiered_recall_l0_by_default_l1_on_high_score():
    calls: list[dict] = []

    def _t(method, url, headers, body, timeout):
        payload = json.loads(body.decode()) if body else {}
        calls.append({"url": url, "payload": payload})
        if url.endswith("/api/v1/search/find"):
            return 200, json.dumps(
                {"results": [
                    {"uri": "viking://resources/a", "score": 0.9},
                    {"uri": "viking://resources/b", "score": 0.3},
                ]}
            ).encode()
        # read：L0/L1/L2 各為 GET 端點，以路徑尾段判別 tier
        tier = url.rsplit("/", 1)[-1].split("?", 1)[0]
        return 200, json.dumps({"content": f"text-{tier}"}).encode()

    viking = OpenVikingClient(config=_cfg("openviking"), transport=_t)
    out = viking.recall_tiered("q", l1_threshold=0.75)
    tiers = {f["uri"]: f["tier"] for f in out["fragments"]}
    assert tiers["viking://resources/a"] == VikingTier.L1_OVERVIEW.value   # 高分升 L1
    assert tiers["viking://resources/b"] == VikingTier.L0_ABSTRACT.value   # 低分留 L0
    # 預設絕不讀 L2 全文
    assert all("/api/v1/content/details" not in c["url"] for c in calls)


def test_openviking_max_tier_l0_forces_abstract_only():
    def _t(method, url, headers, body, timeout):
        if url.endswith("/api/v1/search/find"):
            return 200, json.dumps({"results": [{"uri": "viking://x", "score": 0.99}]}).encode()
        return 200, json.dumps({"content": "abstract-text"}).encode()

    viking = OpenVikingClient(config=_cfg("openviking"), transport=_t)
    out = viking.recall_tiered("q", max_tier=VikingTier.L0_ABSTRACT)
    assert out["fragments"][0]["tier"] == VikingTier.L0_ABSTRACT.value


# ═══════════════════════════════════════════════════════════════
# WeKnora：top-k 段落召回（帶 knowledge_id）
# ═══════════════════════════════════════════════════════════════

def test_weknora_recall_passages_keeps_knowledge_id():
    payload = {"data": [{"knowledge_id": "k1", "content": "第一段"}, {"knowledge_id": "k2", "content": "第二段"}]}
    wk = WeKnoraClient(config=_cfg("weknora"), transport=_transport_ok(payload))
    out = wk.recall_passages("查詢", knowledge_base_id="kb1")
    assert out["degraded"] is False
    assert [f["knowledge_id"] for f in out["fragments"]] == ["k1", "k2"]


# ═══════════════════════════════════════════════════════════════
# Ouroboros：ambiguity 閘門與三階段評估
# ═══════════════════════════════════════════════════════════════

def test_ouroboros_ambiguity_gate_blocks_above_threshold():
    oo = OuroborosClient(config=_cfg("ouroboros"), transport=_transport_ok())
    blocked = oo.gate_seed(AMBIGUITY_GATE + 0.01)
    assert blocked["allowed"] is False and blocked["error_code"] == ERR_AMBIGUITY_GATE_BLOCKED
    assert oo.gate_seed(AMBIGUITY_GATE - 0.01)["allowed"] is True
    # force 為顯式覆寫
    assert oo.gate_seed(0.9, force=True)["forced"] is True


def test_ouroboros_start_auto_blocked_locally_without_remote_call():
    called: list = []
    oo = OuroborosClient(config=_cfg("ouroboros"), transport=lambda *a: called.append(a) or (200, b"{}"))
    out = oo.start_auto("build cli", ambiguity=0.5)
    assert out["ok"] is False and out["error_code"] == ERR_AMBIGUITY_GATE_BLOCKED
    assert called == []  # 閘門在本地阻擋，未打遠端


def test_ouroboros_evaluate_short_circuits_on_stage_failure():
    def _t(method, url, headers, body, timeout):
        payload = json.loads(body.decode())
        stage = payload["params"]["arguments"]["stage"]
        if stage == "semantic":
            return 500, b'{"error": "semantic failed"}'
        return 200, json.dumps({"passed": True}).encode()

    oo = OuroborosClient(config=_cfg("ouroboros"), transport=_t)
    out = oo.evaluate("exec-1")
    assert out["passed"] is False and out["failed_stage"] == "semantic"
    assert [s["stage"] for s in out["stages"]] == ["mechanical"]  # consensus 未執行


def test_ouroboros_convergence_window():
    oo = OuroborosClient(config=_cfg("ouroboros"), transport=_transport_ok())
    assert oo.check_convergence([0.96, 0.97, 0.98])["converged"] is True
    assert oo.check_convergence([0.96, 0.80, 0.99])["converged"] is False
    assert oo.check_convergence([0.99])["converged"] is False  # 世代不足


# ═══════════════════════════════════════════════════════════════
# Yao／OpenPencil：顯式動作
# ═══════════════════════════════════════════════════════════════

def test_yao_and_openpencil_have_no_auto_hooks():
    for cls in (YaoClient, OpenPencilClient):
        for forbidden in ("on_stream_done", "on_chat_complete", "auto_run", "webhook"):
            assert not hasattr(cls, forbidden), f"{cls.__name__} 禁止自動觸發入口：{forbidden}"


def test_openpencil_generate_design_payload():
    seen: list[dict] = []

    def _t(method, url, headers, body, timeout):
        seen.append({"url": url, "payload": json.loads(body.decode())})
        return 200, json.dumps({"design_id": "d1", "canvas_url": "http://x/d1"}).encode()

    op = OpenPencilClient(config=_cfg("openpencil"), transport=_t)
    resp = op.generate_design("做一個登入頁", project_id="p1")
    assert resp.ok is True
    assert seen[0]["url"].endswith("/api/v1/designs/generate")
    assert seen[0]["payload"]["prompt"] == "做一個登入頁"


# ═══════════════════════════════════════════════════════════════
# ContextAssembler：token 節省編排
# ═══════════════════════════════════════════════════════════════

def _history(n: int, size: int = 200) -> list[dict[str, str]]:
    return [{"role": "user" if i % 2 == 0 else "assistant", "content": "字" * size} for i in range(n)]


def test_assembler_windows_history_and_reports_savings():
    assembler = ContextAssembler(memos=None, viking=None, weknora=None, policy=RecallPolicy(history_window=4))
    out = assembler.assemble("q", _history(20, size=100))
    assert len(out.history) == 4                      # 只留最近 4 輪
    report = out.token_report
    assert report["history_dropped_turns"] == 16
    assert report["est_saved_tokens"] >= 0
    assert "recall" in " ".join(out.reason_codes)


def test_assembler_degrades_per_source_and_never_raises():
    memos = MemosClient(config=_cfg("memos"), transport=_transport_down)
    wk = WeKnoraClient(config=_cfg("weknora"), transport=_transport_ok({"data": [{"content": "知識段落", "knowledge_id": "k"}]}))
    assembler = ContextAssembler(memos=memos, viking=None, weknora=wk)
    out = assembler.assemble("q", _history(2), cube_ids=["c1"])
    assert "memos" in out.degraded_sources            # 單源降級不影響其他來源
    assert any(f["source"].startswith("weknora") for f in out.fragments)


def test_assembler_redacts_secrets_before_injection():
    memos = MemosClient(
        config=_cfg("memos"),
        transport=_transport_ok({"data": {"memories": [{"memory": "api_key=sk-SECRETKEY1234567890"}]}}),
    )
    assembler = ContextAssembler(memos=memos, viking=None, weknora=None)
    out = assembler.assemble("q", _history(1), cube_ids=["c1"])
    assert "sk-SECRETKEY1234567890" not in out.render_injection()


def test_assembler_audit_path_bypasses_recall_cache():
    payload = {"data": {"memories": [{"memory": "偏好：繁體中文回覆，內容詳實完整"}]}}
    memos = MemosClient(config=_cfg("memos"), transport=_transport_ok(payload))
    assembler = ContextAssembler(memos=memos, viking=None, weknora=None)
    first = assembler.assemble("q", _history(1), cube_ids=["c1"], audit_path=True)
    assert first.fragments, "審計路徑旁路快取但仍應召回"
    # 審計路徑不得寫入召回快取（C-LLM-003）
    assert assembler.cache.size == 0
