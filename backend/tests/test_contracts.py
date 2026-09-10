"""運行時契約不變式測試（TODO 附錄／docs/contracts/runtime.md）。

每個測試對應一條 CONTRACT-ID；P0 契約失敗應阻斷合併（CI 門檻 §7）。
全部測試可 monkeypatch／stub 隔離，不依賴真實 LLM、外掛遠端或遊戲伺服器。
"""

from __future__ import annotations

import pytest

from backend.company.seat_table import (
    DEPLOY_CONFIRM_SEATS,
    PluginMountPolicy,
    PluginSource,
    build_default_seat_table,
    migrate_task_on_schema_change,
)
from backend.company.state import RoleType
from backend.company.task_state_machine import (
    TaskAction,
    TaskRuntimeState,
    Verdict,
    denied_pairs,
    evaluate,
    queued_pairs,
    transition,
)
from backend.linkin.compiler_pipeline import (
    ERR_DEPLOY_UNAUTHORIZED,
    ERR_RUNTIME_JAVA_FORBIDDEN,
    ERR_SANDBOX_FAILED,
    ArtifactKind,
    CompilePipeline,
    CompileRequest,
    ConflictKind,
    InMemoryArtifactStore,
    InMemoryWorldIndex,
    RecordingDeployer,
    guard_artifact_kind,
    sandbox_scan,
    CompileArtifact,
    _hash_files,
)
from backend.services.conversation_audit import (
    ERR_SNAPSHOT_CONFLICT,
    AuditReport,
    ContextSnapshot,
    ConversationAuditService,
    InMemoryAuditTrailStore,
    PluginPin,
    compute_plugin_set_hash,
)
from backend.company.raho import arbitration
from backend.company.raho.arbitration import (
    ARBITRATION_KIND,
    RULING_ACCEPT_L1,
    raise_l1_dispute,
    resolve_l1_dispute,
)
from backend.company.raho.l0_pipeline import (
    CoreKind,
    L0Pipeline,
    PIPELINE_ORDER,
    REASON_CORE_DISABLED,
    REASON_REDACTED,
    compute_pressure,
    default_pressure_weights,
    injection_strength,
    redact,
)
from backend.linkin.narrative_workspace import (
    CHOICE_REBIND,
    ERR_SNAPSHOT_UNRESOLVED,
    WorkspaceRegistry,
    WorkspaceState,
)
from backend.scripts.lint_contracts import scan as lint_scan
from backend.scripts.lint_contracts import scan_file as lint_scan_file
from backend.company.raho.store import STORE as RAHO_STORE


# ═══════════════════════════════════════════════════════════════
# §1 對話審計契約（P0）
# ═══════════════════════════════════════════════════════════════

def _snapshot(tag: str = "a") -> ContextSnapshot:
    return ContextSnapshot(
        conversation_snapshot_id=f"conv-{tag}",
        l0_snapshot_id=f"l0-{tag}",
        seat_schema_version="1.0.0",
        plugin_set_hash=compute_plugin_set_hash([PluginPin("p1", "1.0.0", True)]),
    )


def _service(snapshots: dict[str, ContextSnapshot] | None = None, **kwargs) -> ConversationAuditService:
    snaps = snapshots if snapshots is not None else {}
    return ConversationAuditService(snapshot_provider=lambda tid: snaps.get(tid, _snapshot()), **kwargs)


def test_contract_c_audit_001_no_auto_audit_entrypoint():
    """C-AUDIT-001：無串流／webhook 自動觸發入口；未請求時無審計結果。"""
    svc = _service()
    svc.register_task("t1")
    task = svc.get("t1")
    assert task.report is None
    assert task.state is TaskRuntimeState.RUNNING
    # 服務介面僅暴露顯式動作：request_audit／resume／confirm
    for forbidden in ("on_stream_done", "on_chat_complete", "auto_audit", "webhook"):
        assert not hasattr(svc, forbidden), f"禁止自動觸發入口：{forbidden}"


def test_contract_c_audit_002_pause_before_audit_sequence():
    """C-AUDIT-002：running 上 audit 必經「等 inflight → paused → auditing」。"""
    events: list[str] = []
    svc = _service(inflight_waiter=lambda tid: events.append(f"wait:{tid}"))
    svc.register_task("t1")
    out = svc.request_audit("t1")
    assert out["ok"] is True
    assert events == ["wait:t1"]                     # 先等 inflight（禁止強制 abort）
    assert svc.get("t1").frozen is not None          # 進 paused 時已凍結快照
    assert svc.get("t1").state is TaskRuntimeState.PAUSED  # 結果展示後保持 paused


def test_contract_c_audit_003_failure_keeps_paused_no_fake_score():
    """C-AUDIT-003：審計失敗預設保持 paused，不寫入假分數。"""

    def boom(task_id, snapshot, trail):
        raise RuntimeError("runner exploded")

    svc = _service(audit_runner=boom)
    svc.register_task("t1")
    out = svc.request_audit("t1")
    assert out["ok"] is False
    assert out["error_code"] == "ERR_AUDIT_FAILED"
    assert svc.get("t1").state is TaskRuntimeState.PAUSED
    assert svc.get("t1").report is None  # 禁止靜默寫入假分數


def test_contract_c_audit_004_plugin_hash_includes_pin_version():
    """C-AUDIT-004：插件集合雜湊輸入＝ID＋pin 版本＋啟用狀態；僅升版即衝突。"""
    base = compute_plugin_set_hash([PluginPin("dsh-x", "1.2.0", True)])
    bumped = compute_plugin_set_hash([PluginPin("dsh-x", "1.2.1", True)])
    toggled = compute_plugin_set_hash([PluginPin("dsh-x", "1.2.0", False)])
    assert base != bumped, "pin 版本變更必須改變雜湊"
    assert base != toggled, "啟停狀態變更必須改變雜湊"


def test_contract_c_audit_005_trail_is_append_only_and_purge_audited():
    """C-AUDIT-005：軌跡 append-only（無 update/delete）；purge 為可審計管理動作。"""
    admin_events: list[dict] = []
    store = InMemoryAuditTrailStore(admin_log=admin_events.append)
    store.append("t1", {"type": "compile_start"})
    store.append("t1", {"type": "deployed"})
    assert len(store.read("t1")) == 2
    assert not hasattr(store, "update") and not hasattr(store, "delete")
    assert store.purge("t1") == 2
    assert admin_events and admin_events[0]["action"] == "purge_audit_trail"


def test_contract_c_audit_006_resume_conflict_goes_awaiting_confirmation():
    """C-AUDIT-006（§1.5／§9.1）：快照衝突禁止靜默續跑；確認後才可離開。"""
    snaps = {"t1": _snapshot("a")}
    svc = _service(snapshots=snaps)
    svc.register_task("t1")
    assert svc.request_audit("t1")["ok"] is True
    snaps["t1"] = _snapshot("b")  # L0 刷新導致快照變更
    out = svc.resume("t1")
    assert out["ok"] is False
    assert out["error_code"] == ERR_SNAPSHOT_CONFLICT
    assert svc.get("t1").state is TaskRuntimeState.AWAITING_CONFIRMATION
    assert "conversation_snapshot_id" in out["conflict_diff"]
    # 衝突未確認前部署被拒（矩陣聯動）
    assert evaluate(TaskRuntimeState.AWAITING_CONFIRMATION, TaskAction.DEPLOY).verdict is Verdict.DENY
    rebound = svc.confirm("t1", "rebind")
    assert rebound["ok"] is True and rebound["rebound"] is True


# ═══════════════════════════════════════════════════════════════
# §2 指揮鏈席位表契約（P0）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_seat_001_schema_version_and_freeze_on_change():
    """C-SEAT-001：席位表帶 schema_version；變更時舊任務凍結而非靜默改寫。"""
    table = build_default_seat_table()
    assert table.schema_version
    assert migrate_task_on_schema_change(table.schema_version, table.schema_version) == "unchanged"
    assert migrate_task_on_schema_change(table.schema_version, "9.9.9") == "frozen"


def test_contract_c_seat_002_deploy_confirm_defaults_to_l5_and_human_only():
    """C-SEAT-002（§8.2）：部署確認權預設僅 L5 用戶＋人類管理員。"""
    table = build_default_seat_table()
    assert DEPLOY_CONFIRM_SEATS == frozenset({"l5_user", "human_admin"})
    assert table.has_deploy_confirm("l5_user") is True
    assert table.has_deploy_confirm("human_admin") is True
    for seat in table.seats.values():
        assert seat.deploy_confirm is False, f"{seat.role_id} 不得預設持有部署確認權"
    assert table.has_deploy_confirm(RoleType.MANAGER.value) is False


def test_contract_c_seat_003_l0_has_no_tools_or_plugins():
    """C-SEAT-003（§4.1）：L0 注入席無工具、無插件白名單、不執行任務。"""
    table = build_default_seat_table()
    l0 = table.seat(RoleType.ENVIRONMENT_KERNEL.value)
    assert l0 is not None and l0.raho_layer == "L0"
    assert l0.tool_scope == () and l0.plugin_whitelist == ()
    verdict = table.check_plugin_mount(
        l0.role_id, PluginMountPolicy("p", PluginSource.DSH_PLUGIN)
    )
    assert verdict.ok is False and "ERR_L0_NO_PLUGIN" in verdict.reason


def test_contract_c_seat_004_plugin_mount_level_cap():
    """C-SEAT-004（§2.4／§6.4）：插件掛載受最高層級上限與白名單雙向約束。"""
    from backend.company.seat_table import SeatSpec, SeatTable

    seats = {
        "l3_cmd": SeatSpec("l3_cmd", "L3", raho_layer="L3", plugin_whitelist=("p1",)),
        "l2_exec": SeatSpec("l2_exec", "L2", raho_layer="L2", plugin_whitelist=("p1",)),
    }
    table = SeatTable(schema_version="t", seats=seats)
    policy = PluginMountPolicy("p1", PluginSource.DSH_PLUGIN, max_mount_layer="L2", pin_version="1.0.0")
    assert table.check_plugin_mount("l2_exec", policy).ok is True
    denied = table.check_plugin_mount("l3_cmd", policy)
    assert denied.ok is False and "ERR_PLUGIN_MOUNT_LEVEL" in denied.reason
    not_listed = table.check_plugin_mount(
        "l2_exec", PluginMountPolicy("p2", PluginSource.DSH_PLUGIN, max_mount_layer="L2")
    )
    assert not_listed.ok is False and "ERR_PLUGIN_NOT_WHITELISTED" in not_listed.reason


# ═══════════════════════════════════════════════════════════════
# §9 狀態組合矩陣契約（P1，骨架先行）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_state_001_every_denial_has_error_code():
    """C-STATE-001（§9.1／§9.2）：所有 ✗ 路徑必附可觀測錯誤碼。"""
    pairs = denied_pairs()
    assert pairs, "矩陣必須定義拒絕路徑"
    for state, action, code in pairs:
        assert code.startswith("ERR_"), f"{state.value}×{action.value} 缺錯誤碼"


def test_contract_c_state_002_auditing_freezes_snapshot_and_plugins():
    """C-STATE-002（§9.1）：審計中禁止 L0 刷新與插件集合變更。"""
    assert evaluate(TaskRuntimeState.AUDITING, TaskAction.L0_REFRESH).verdict is Verdict.DENY
    assert evaluate(TaskRuntimeState.AUDITING, TaskAction.PLUGIN_TOGGLE).verdict is Verdict.DENY


def test_contract_c_state_003_l0_refreshing_audit_is_queued():
    """C-STATE-003（§9）：l0_refreshing 下 audit 佇列，刷新後自動 paused→auditing。"""
    decision = evaluate(TaskRuntimeState.L0_REFRESHING, TaskAction.AUDIT)
    assert decision.verdict is Verdict.QUEUE
    assert "auditing" in decision.note


def test_contract_c_state_004_compiling_denies_audit_and_deploy():
    """C-STATE-004（§9.1）：編譯／沙盒中禁止審計；編譯結束後才可審計完整軌跡。"""
    for state in (TaskRuntimeState.COMPILING, TaskRuntimeState.SANDBOXING):
        assert evaluate(state, TaskAction.AUDIT).verdict is Verdict.DENY
        assert evaluate(state, TaskAction.DEPLOY).verdict is Verdict.DENY


def test_contract_c_state_005_denial_never_transitions():
    """C-STATE-005（§9.1）：✗／Q 路徑不改變既有狀態（保護凍結快照）。"""
    for state, action, _ in denied_pairs():
        assert transition(state, action) is state
    for state, action in queued_pairs():
        assert transition(state, action) is state


def test_contract_c_state_006_awaiting_deploy_pause_semantics():
    """C-STATE-006（§9.1）：awaiting_deploy 下 pause 暫停任務生命週期，審批獨立。"""
    decision = evaluate(TaskRuntimeState.AWAITING_DEPLOY, TaskAction.PAUSE)
    assert decision.verdict is Verdict.ALLOW
    assert "部署審批流程獨立" in decision.note


# ═══════════════════════════════════════════════════════════════
# §8 MC 編譯器契約（P0）
# ═══════════════════════════════════════════════════════════════

def _pipeline(**kwargs) -> tuple[CompilePipeline, RecordingDeployer, InMemoryArtifactStore]:
    store = kwargs.pop("store", InMemoryArtifactStore())
    deployer = kwargs.pop("deployer", RecordingDeployer())
    return CompilePipeline(store=store, deployer=deployer, **kwargs), deployer, store


def test_contract_c_comp_001_explicit_compile_and_sandbox_gate():
    """C-COMP-001：編譯顯式觸發；沙盒通過才進 awaiting_deploy；不自動部署。"""
    pipeline, deployer, store = _pipeline()
    req = CompileRequest(namespace="quest_a", kind=ArtifactKind.DATAPACK, files={"data/quest_a/a.mcfunction": "say hi"})
    out = pipeline.compile("task-1", req)
    assert out.ok is True
    assert out.state is TaskRuntimeState.AWAITING_DEPLOY
    assert deployer.deployed == []            # 編譯成功 ≠ 自動部署
    assert store.latest("quest_a") is None    # 線上版本未被覆蓋


def test_contract_c_comp_002_failure_keeps_old_version_no_reload():
    """C-COMP-002：沙盒失敗保留舊版本、禁止自動 /reload。"""
    pipeline, deployer, store = _pipeline()
    ok_req = CompileRequest(namespace="quest_a", kind=ArtifactKind.DATAPACK, files={"a.mcfunction": "say 1"})
    first = pipeline.compile("task-1", ok_req)
    assert first.ok and first.artifact is not None
    deployed = pipeline.deploy("task-1", first.artifact.artifact_id, confirmed_by="l5_user")
    assert deployed.ok is True
    # 第二次編譯：產物含 .java → 沙盒結構校驗失敗
    bad_req = CompileRequest(namespace="quest_a", kind=ArtifactKind.DATAPACK, files={"Evil.java": "class Evil {}"})
    failed = pipeline.compile("task-2", bad_req)
    assert failed.ok is False and failed.error_code == ERR_SANDBOX_FAILED
    assert store.latest("quest_a").version == 1  # 舊版本保留
    assert deployer.reload_calls == 0            # 禁止自動 /reload


def test_contract_c_comp_003_runtime_java_forbidden():
    """C-COMP-003（§8.6）：禁止運行時生成／編譯 Java；形態優先級寫死。"""
    with pytest.raises(ValueError, match=ERR_RUNTIME_JAVA_FORBIDDEN):
        guard_artifact_kind(ArtifactKind.JAVA_MOD_RUNTIME)
    pipeline, _, _ = _pipeline()
    req = CompileRequest(namespace="x", kind=ArtifactKind.JAVA_MOD_RUNTIME, files={"A.java": "..."})
    assert pipeline.compile("task-1", req).error_code == ERR_RUNTIME_JAVA_FORBIDDEN


def test_contract_c_comp_004_deploy_requires_confirm_seat():
    """C-COMP-004（§8.2）：未具部署確認權的席位不得部署；確認動作可審計。"""
    trail: list[tuple[str, dict]] = []
    pipeline, deployer, _ = _pipeline(trail=lambda tid, ev: trail.append((tid, ev)))
    req = CompileRequest(namespace="quest_a", kind=ArtifactKind.DATAPACK, files={"a.mcfunction": "say 1"})
    out = pipeline.compile("task-1", req)
    assert out.ok and out.artifact is not None
    denied = pipeline.deploy("task-1", out.artifact.artifact_id, confirmed_by=RoleType.ATOMIC_EXECUTOR.value)
    assert denied.ok is False and denied.error_code == ERR_DEPLOY_UNAUTHORIZED
    assert deployer.deployed == []
    approved = pipeline.deploy("task-1", out.artifact.artifact_id, confirmed_by="human_admin")
    assert approved.ok is True
    assert any(ev["type"] == "deployed" for _, ev in trail)


def test_contract_c_comp_005_sandbox_scans_five_conflict_kinds():
    """C-COMP-005（§8.2）：衝突掃描涵蓋命名空間／實體 ID／配方／戰利品表／標籤。"""
    artifact = CompileArtifact(
        artifact_id="a1",
        namespace="dup_ns",
        kind=ArtifactKind.DATAPACK,
        version=1,
        content_hash=_hash_files({"f": "x"}),
        files={"f": "x"},
        entity_ids=("zombie_custom",),
        recipes=("bread_x",),
        loot_tables=("chests/x",),
        tags=("minecraft:logs",),
    )
    world = InMemoryWorldIndex(
        namespaces=("dup_ns",),
        entity_ids=("zombie_custom",),
        recipes=("bread_x",),
        loot_tables=("chests/x",),
        tags=("minecraft:logs",),
    )
    report = sandbox_scan(artifact, world)
    assert report.ok is False
    kinds = {c.kind for c in report.conflicts}
    assert kinds == {
        ConflictKind.NAMESPACE,
        ConflictKind.ENTITY_ID,
        ConflictKind.RECIPE,
        ConflictKind.LOOT_TABLE,
        ConflictKind.TAG,
    }


# ═══════════════════════════════════════════════════════════════
# §2 補強：繞過指揮鏈 lint＋L1 仲裁（P0）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_seat_005_lint_no_orchestrator_bypass(tmp_path):
    """C-SEAT-005：modules／linkin 層直連 L2 執行席會被 lint 偵測並拒絕。"""
    bad = tmp_path / "backend" / "modules" / "evil.py"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        "from backend.company.raho.atomic_executor import AtomicExecutor\n",
        encoding="utf-8",
    )
    hits = lint_scan_file(bad, tmp_path)
    assert [h.rule for h in hits] == ["no_orchestrator_bypass"]
    # 現有倉庫必須零違規（CI 門檻）
    assert [v for v in lint_scan(".") if v.rule == "no_orchestrator_bypass"] == []


def test_contract_c_llm_001_lint_no_direct_provider_sdk(tmp_path):
    """C-LLM-001：業務代碼直連供應商 SDK 會被 lint 拒絕；調用層豁免。"""
    bad = tmp_path / "backend" / "linkin" / "rogue.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("import openai\nopenai.chat.completions.create()\n", encoding="utf-8")
    hits = lint_scan_file(bad, tmp_path)
    assert [h.rule for h in hits] == ["no_direct_provider_sdk"]
    # 合法調用層（litellm 集中在 core／memory）不誤報
    ok = tmp_path / "backend" / "core" / "llm.py"
    ok.parent.mkdir(parents=True)
    ok.write_text("from litellm import completion\n", encoding="utf-8")
    assert lint_scan_file(ok, tmp_path) == []
    assert [v for v in lint_scan(".") if v.rule == "no_direct_provider_sdk"] == []


def test_contract_c_seat_006_l1_dispute_goes_to_l5_not_executor():
    """C-SEAT-006：L1 攔截爭議只能升級 L5／人工；執行席無自行推翻入口。"""
    # 契約：仲裁模組刻意不提供任何 override／force 入口
    for forbidden in ("override", "force_approve", "executor_override"):
        assert not hasattr(arbitration, forbidden), f"禁止執行席推翻入口：{forbidden}"
    # 同步路徑預設接受 L1（推翻只能走 L5 async 裁決）
    out = resolve_l1_dispute(
        run_id="r1",
        item_id="i1",
        l1_verdict="ESCALATE",
        l1_reason="事實一致性失敗且修正耗盡",
        executor_claim="L3 堅持執行",
    )
    assert out["choice"] == RULING_ACCEPT_L1
    # 可觀測：爭議與裁決都留下節點
    dispute = raise_l1_dispute(
        run_id="r1", item_id="i2", l1_verdict="REWORK", l1_reason="結構不合規"
    )
    assert dispute.dispute_id
    tree = next(t for t in RAHO_STORE.list_trees() if t.run_id == "r1")
    kinds = [n.kind for n in tree.nodes]
    assert ARBITRATION_KIND in kinds and f"{ARBITRATION_KIND}_ruling" in kinds


# ═══════════════════════════════════════════════════════════════
# §4 L0 三核管線（P1）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_l0_001_pipeline_bypass_and_reason_codes():
    """C-L0-001：預設串行三核；單核旁路時下游降級輸入＋路由原因碼。"""
    order = [c.value for c in PIPELINE_ORDER]
    assert order == ["memory", "graph", "bias"]  # 記憶 → 圖譜 → 態勢
    seen: list[dict] = []

    def graph_spy(**kw):
        seen.append(kw)
        return ["node-a"]

    pipe = L0Pipeline(
        cores={
            CoreKind.MEMORY: lambda **_: ["mem-1"],
            CoreKind.GRAPH: graph_spy,
            CoreKind.BIAS: lambda **_: ["bias-1"],
        }
    )
    pipe.enabled[CoreKind.MEMORY] = False  # 旁路記憶核
    out = pipe.run("q", pressure=0.0)
    memory = next(c for c in out.cores if c.core is CoreKind.MEMORY)
    assert memory.bypassed is True and memory.reason_code == REASON_CORE_DISABLED
    assert seen[0]["memory"] == []          # 下游拿到降級輸入（空片段）
    assert "memory:core_disabled" in out.reason_codes
    assert "node-a" in out.fragments and "bias-1" in out.fragments


def test_contract_c_l0_002_injection_redaction():
    """C-L0-002：密鑰／憑證／PII 在注入前被遮罩，且原因碼可觀測。"""
    text, hit = redact("endpoint https://x api_key=sk-ABCDEFGHIJKL123456 聯絡 a@b.com")
    assert hit is True
    assert "sk-ABCDEFGHIJKL123456" not in text and "a@b.com" not in text
    pipe = L0Pipeline(
        cores={
            CoreKind.MEMORY: lambda **_: ["password= hunters2 正常片段"],
            CoreKind.GRAPH: lambda **_: [],
            CoreKind.BIAS: lambda **_: [],
        }
    )
    out = pipe.run("q")
    assert "hunters2" not in "".join(out.fragments)
    assert f"memory:{REASON_REDACTED}" in out.reason_codes


def test_contract_c_l0_003_pressure_drives_injection_strength():
    """C-L0-003：預設等權歸一化；壓力上升 → 注入片段實際減少（非死數字）。"""
    weights = default_pressure_weights()
    assert len(set(weights.values())) == 1  # 等權
    low = compute_pressure({"queue_depth": 0.1, "error_rate": 0.1})
    high = compute_pressure({name: 1.0 for name in weights})
    assert 0.0 <= low < high <= 1.0
    assert injection_strength(high) < injection_strength(low)
    pipe = L0Pipeline(
        cores={
            CoreKind.MEMORY: lambda **_: [f"m{i}" for i in range(10)],
            CoreKind.GRAPH: lambda **_: [],
            CoreKind.BIAS: lambda **_: [],
        }
    )
    calm = pipe.run("q", pressure=0.0)
    storm = pipe.run("q", pressure=1.0)
    assert len(storm.fragments) < len(calm.fragments)  # 壓力驅動注入強度


# ═══════════════════════════════════════════════════════════════
# §4.7 敘事臨時工作區（P1）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_l0_004_narrative_workspace_no_dual_write():
    """C-L0-004：工作區無圖譜寫入入口；落庫必經顯式 writer；快照衝突預設待確認。"""
    for forbidden in ("write_graph", "put_entity", "upsert_relation"):
        assert not hasattr(WorkspaceRegistry, forbidden), f"禁止第二套可寫圖譜：{forbidden}"
    reg = WorkspaceRegistry()
    ws = reg.begin("task-1", snapshot_id="snap-a")
    assert ws.workspace_id and ws.snapshot_id == "snap-a"
    assert reg.write_draft(ws.workspace_id, "branch", {"choice": "open"}).ok is True
    # L0 刷新 → 快照變更 → 預設 awaiting_confirmation（保留成果，不丟棄）
    assert reg.on_l0_refresh("snap-b") == [ws.workspace_id]
    assert reg.get(ws.workspace_id).state is WorkspaceState.AWAITING_CONFIRMATION
    # 快照未確認前禁止落庫
    assert reg.commit(ws.workspace_id, writer=lambda d: None).error_code == ERR_SNAPSHOT_UNRESOLVED
    # 顯式重綁後才可經 writer 落庫
    assert reg.confirm(ws.workspace_id, CHOICE_REBIND, new_snapshot_id="snap-b").ok is True
    written: list[dict] = []
    assert reg.commit(ws.workspace_id, writer=written.append).ok is True
    assert written == [{"branch": {"choice": "open"}}]
    # 任務結束＝生命週期上限：未提交草稿自動丟棄
    ws2 = reg.begin("task-2", snapshot_id="snap-b")
    reg.write_draft(ws2.workspace_id, "draft", "x")
    assert reg.end_task("task-2") == 1
    assert reg.get(ws2.workspace_id).state is WorkspaceState.DISCARDED


# ═══════════════════════════════════════════════════════════════
# §5 降 LLM 依賴契約（P1）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_llm_002_route_reason_codes():
    """C-LLM-002：可程式化決策走程式碼路徑且附原因碼；經 LLM 決定直接拒絕。"""
    from backend.core.decision_router import (
        ERR_LLM_FORBIDDEN_FOR_ACTION,
        REASON_NEEDS_GENERATION,
        REASON_PROGRAMMATIC_ACTION,
        DecisionAction,
        DecisionRouter,
        RouteTarget,
    )

    router = DecisionRouter()
    # 全部白名單動作短路，不進 LLM
    for action in DecisionAction:
        d = router.route_action(action)
        assert d.target is RouteTarget.PROGRAMMATIC
        assert d.reason_code == REASON_PROGRAMMATIC_ACTION
    # 可觀測：每次短路都有原因碼（「為什麼沒走 LLM」可回答）
    assert len(router.reason_codes()) == len(list(DecisionAction))
    # 生成類需求才進 LLM，原因碼同樣記錄
    gen = router.route_generation(detail="產出任務計畫段落")
    assert gen.target is RouteTarget.LLM and gen.reason_code == REASON_NEEDS_GENERATION
    # 契約守衛：可程式化決策試圖經 LLM → 拒絕
    with pytest.raises(ValueError, match=ERR_LLM_FORBIDDEN_FOR_ACTION):
        router.guard_programmatic_action(DecisionAction.DEPLOY_ARTIFACT, via_llm=True)
    router.guard_programmatic_action(DecisionAction.PAUSE_TASK, via_llm=False)  # 不拋例外


def test_contract_c_llm_003_cache_bypass_audit_paths():
    """C-LLM-003：分類型 TTL；審計／憲兵路徑預設旁路（TTL=0），禁止誤傷新鮮上下文。"""
    from backend.core.typed_llm_cache import (
        REASON_BYPASS_AUDIT,
        REASON_BYPASS_INSPECTOR,
        REASON_CACHE_HIT,
        REASON_CACHE_MISS,
        CacheKind,
        TypedLLMCache,
    )

    cache = TypedLLMCache()
    # 審計／憲兵：寫入被拒、查詢必旁路
    assert cache.put(CacheKind.AUDIT_CONTEXT, "k", "v") is False
    assert cache.put(CacheKind.INSPECTOR_CONTEXT, "k", "v") is False
    assert cache.get(CacheKind.AUDIT_CONTEXT, "k").reason_code == REASON_BYPASS_AUDIT
    assert cache.get(CacheKind.INSPECTOR_CONTEXT, "k").reason_code == REASON_BYPASS_INSPECTOR
    # 受保護路徑禁止設 TTL > 0（除非顯式覆寫）
    with pytest.raises(ValueError):
        cache.set_ttl(CacheKind.AUDIT_CONTEXT, 60.0)
    # 分類型 TTL 差異：角色 Prompt 長、評估短
    assert cache.ttl_for(CacheKind.ROLE_PROMPT) > cache.ttl_for(CacheKind.EVALUATION) > 0
    # 一般類型正常命中／未命中，原因碼可觀測
    assert cache.get(CacheKind.ROLE_PROMPT, "k1").reason_code == REASON_CACHE_MISS
    assert cache.put(CacheKind.ROLE_PROMPT, "k1", "prompt-frag") is True
    hit = cache.get(CacheKind.ROLE_PROMPT, "k1")
    assert hit.hit is True and hit.value == "prompt-frag" and hit.reason_code == REASON_CACHE_HIT
    # TTL 過期淘汰（注入假時鐘）
    now = [1000.0]
    timed = TypedLLMCache(clock=lambda: now[0])
    timed.put(CacheKind.EVALUATION, "k", "score")
    now[0] += timed.ttl_for(CacheKind.EVALUATION) + 1
    assert timed.get(CacheKind.EVALUATION, "k").hit is False


def test_contract_c_llm_004_small_model_escalation_cap():
    """C-LLM-004：小模型預設先行；啟發式不達標才升級；升級有次數上限＋成本記錄。"""
    from backend.core.small_model_router import (
        REASON_ESCALATED,
        REASON_ESCALATION_CAP_REACHED,
        REASON_SMALL_MODEL_OK,
        SmallModelRouter,
        heuristic_score,
    )

    router = SmallModelRouter(escalation_cap=2)
    good = "這是一段足夠長且結構正常的小模型輸出結果，可直接使用。"
    bad = "TODO"
    # 達標：留在小模型
    out = router.route("t1", good)
    assert out["usable"] is True and out["escalated"] is False
    assert out["reason_code"] == REASON_SMALL_MODEL_OK and out["model"] == router.small_model
    # 不達標：升級大模型（第 1、2 次允許）
    for attempt in (1, 2):
        up = router.route("t1", bad)
        assert up["escalated"] is True and up["reason_code"] == REASON_ESCALATED
        assert up["model"] == router.large_model and up["attempt"] == attempt
    # 第 3 次：超過上限，拒絕升級且輸出標記不可用
    cap = router.route("t1", bad)
    assert cap["escalated"] is False and cap["usable"] is False
    assert cap["reason_code"] == REASON_ESCALATION_CAP_REACHED
    # 成本觀測：恰好 2 筆升級記錄，含原因與模型對
    assert len(router.cost_log) == 2
    assert router.cost_log[0].reason == "too_short"
    assert router.cost_log[0].from_model == router.small_model
    # 啟發式規則本身可測
    assert heuristic_score("")[0] is False
    assert heuristic_score("抱歉，我無法回答這個問題，內容不足。")[0] is False
    assert heuristic_score(good)[0] is True


# ═══════════════════════════════════════════════════════════════
# §6 插件整合契約（P2）
# ═══════════════════════════════════════════════════════════════

def test_contract_c_plugin_001_no_auto_plugin_install():
    """C-PLUGIN-001：安裝／啟用為顯式動作；無串流／webhook 自動觸發入口。"""
    from backend.modules.plugin_manager import (
        ERR_PLUGIN_VERSION_NOT_REVIEWED,
        PluginManager,
    )

    mgr = PluginManager()
    # 刻意不存在自動觸發入口
    for forbidden in ("on_stream_done", "on_chat_complete", "auto_install", "auto_enable", "webhook"):
        assert not hasattr(mgr, forbidden), f"禁止自動安裝入口：{forbidden}"
    # 未經顯式動作 → 無任何插件
    assert mgr.plugins == {}
    # 顯式安裝但預設要求 pin 版本（禁止浮動）
    out = mgr.install("dsh-x", "deepseek-club/dsh-plugin", version=None)
    assert out["ok"] is False and out["error_code"] == ERR_PLUGIN_VERSION_NOT_REVIEWED
    assert mgr.plugins == {}
    # 顯式安裝＋pin 版本 → installed（非自動啟用）
    ok = mgr.install("dsh-x", "deepseek-club/dsh-plugin", version="1.2.0")
    assert ok["ok"] is True and ok["status"] == "installed"


def test_contract_c_plugin_002_plugin_degrade_keeps_trail():
    """C-PLUGIN-002：降級／停用不丟已記錄呼叫日誌；審計讀軌跡與插件可用性無關。"""
    from backend.modules.plugin_manager import PluginManager, PluginStatus

    mgr = PluginManager()
    mgr.install("dsh-x", "deepseek-club/dsh-plugin", version="1.2.0")
    mgr.enable("dsh-x")
    mgr.record_call("dsh-x", {"tool": "search", "args": {"q": "a"}})
    mgr.record_call("dsh-x", {"tool": "search", "args": {"q": "b"}})
    mgr.degrade("dsh-x", reason="timeout")
    assert mgr.plugins["dsh-x"].status is PluginStatus.DEGRADED
    # 降級後呼叫被拒，但歷史軌跡完整可查
    assert mgr.record_call("dsh-x", {"tool": "search"})["ok"] is False
    trail = mgr.audit_trail("dsh-x")
    calls = [e for e in trail if e["type"] == "plugin_call"]
    assert len(calls) == 2  # 降級前的記錄沒丟
    assert any(e["type"] == "plugin_degraded" for e in trail)
    # 停用同樣保留
    mgr2 = PluginManager()
    mgr2.install("p", "deepseek-club/dsh-plugin", version="1.0.0")
    mgr2.enable("p")
    mgr2.record_call("p", {"tool": "t"})
    mgr2.disable("p")
    assert len([e for e in mgr2.audit_trail("p") if e["type"] == "plugin_call"]) == 1


def test_contract_c_plugin_003_dsh_plugin_pin_default():
    """C-PLUGIN-003：預設手動 pin；非白名單倉庫／未審核版本一律拒絕。"""
    from backend.modules.plugin_manager import (
        ERR_PLUGIN_REPO_NOT_WHITELISTED,
        ERR_PLUGIN_VERSION_NOT_REVIEWED,
        PluginManager,
        PluginSourcePolicy,
    )

    mgr = PluginManager()
    # 預設政策：手動 pin 為必須
    assert mgr.policy.default_pin_required is True
    # 非白名單倉庫 → 拒絕
    out = mgr.install("rogue", "unknown-org/evil", version="9.9.9")
    assert out["ok"] is False and out["error_code"] == ERR_PLUGIN_REPO_NOT_WHITELISTED
    # 白名單倉庫但未審核版本（設定了審核清單時）→ 拒絕
    strict = PluginManager(
        policy=PluginSourcePolicy(reviewed_versions=frozenset({"1.2.0"}))
    )
    out = strict.install("dsh-x", "deepseek-club/dsh-plugin", version="1.3.0-rc1")
    assert out["ok"] is False and out["error_code"] == ERR_PLUGIN_VERSION_NOT_REVIEWED
    ok = strict.install("dsh-x", "deepseek-club/dsh-plugin", version="1.2.0")
    assert ok["ok"] is True
    # 無任何遠端腳本執行入口（禁止執行未審核遠端腳本）
    for forbidden in ("run_remote_script", "exec_remote", "fetch_and_run"):
        assert not hasattr(PluginManager, forbidden), f"禁止遠端腳本入口：{forbidden}"


# ── C-PERF-001 / C-UI-002 ──────────────────────────────────────


def test_contract_c_perf_001_stubbed_clock_budgets():
    """C-PERF-001（§7.2）：P95 預設上限可用 stub 耗時驗證。"""
    from backend.core.perf_budget import (
        DEFAULT_P95_SECONDS,
        ERR_PERF_BUDGET_EXCEEDED,
        assert_within_budget,
        check_elapsed,
    )

    assert DEFAULT_P95_SECONDS["l0_refresh"] == 3.0
    assert DEFAULT_P95_SECONDS["plugin_toggle"] == 2.0
    assert DEFAULT_P95_SECONDS["compile_pipeline_stub"] == 5.0
    assert DEFAULT_P95_SECONDS["audit_no_llm"] == 1.0

    ok = check_elapsed("l0_refresh", 2.9)
    assert ok.ok is True
    bad = check_elapsed("l0_refresh", 3.01)
    assert bad.ok is False
    assert bad.error_code == ERR_PERF_BUDGET_EXCEEDED

    assert_within_budget("audit_no_llm", 0.5)
    try:
        assert_within_budget("audit_no_llm", 1.5)
        raise AssertionError("expected TimeoutError")
    except TimeoutError as exc:
        assert ERR_PERF_BUDGET_EXCEEDED in str(exc)


def test_contract_c_ui_002_button_enabled_matches_deny_matrix():
    """C-UI-002（§9.2）：按鈕可用性 = 非 DENY；與 denied_pairs 一致。"""
    from backend.company.task_state_machine import (
        TaskAction,
        TaskRuntimeState,
        button_enabled,
        denied_pairs,
        evaluate,
        export_matrix,
        Verdict,
    )

    for state, action, code in denied_pairs():
        assert button_enabled(state, action) is False
        assert evaluate(state, action).error_code == code

    # 已知允許組合
    assert button_enabled(TaskRuntimeState.RUNNING, TaskAction.PAUSE) is True
    assert button_enabled(TaskRuntimeState.PAUSED, TaskAction.AUDIT) is True
    assert button_enabled(TaskRuntimeState.L0_REFRESHING, TaskAction.AUDIT) is True  # QUEUE
    assert button_enabled(TaskRuntimeState.AUDITING, TaskAction.RESUME) is False

    exported = export_matrix()
    assert exported["schema"] == "todo-§9-v1"
    deny_cells = [c for c in exported["cells"] if c["verdict"] == Verdict.DENY.value]
    assert len(deny_cells) == len(denied_pairs())
    for cell in deny_cells:
        assert cell["button_enabled"] is False
        assert cell["error_code"]
