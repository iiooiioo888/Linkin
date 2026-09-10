"""任務運行時狀態組合矩陣（TODO §9）。

單任務視角的狀態機骨架：

- ``TaskRuntimeState``：`running / paused / auditing / l0_refreshing /
  plugin_degraded / compiling / sandboxing / awaiting_deploy / awaiting_confirmation`
- ``TaskAction``：`pause / audit / resume / l0_refresh / plugin_toggle / compile / deploy`
- ``evaluate(state, action)``：回傳 ``Decision``（ALLOW／DENY／QUEUE／SEQUENCE），
  DENY 一律附**衝突錯誤碼**（§9.1：可觀測錯誤碼＋不改變既有凍結快照）。
- ``transition(state, action)``：對 ALLOW／SEQUENCE 給出下一狀態。

粒度聲明（§9）：本矩陣以**單任務視角**描述；全局狀態（插件全局降級、L0 全局刷新）
與任務狀態的組合規則另文定義，實作時不得預設共享或隔離。

UI 契約（§9.2）：前端按鈕可用性必須以本矩陣為準，禁止前端自行放行後端會拒絕的組合。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskRuntimeState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    AUDITING = "auditing"
    L0_REFRESHING = "l0_refreshing"
    PLUGIN_DEGRADED = "plugin_degraded"
    COMPILING = "compiling"
    SANDBOXING = "sandboxing"
    AWAITING_DEPLOY = "awaiting_deploy"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 快照衝突待確認（§1.5）


class TaskAction(str, Enum):
    PAUSE = "pause"
    AUDIT = "audit"
    RESUME = "resume"
    L0_REFRESH = "l0_refresh"
    PLUGIN_TOGGLE = "plugin_toggle"
    COMPILE = "compile"
    DEPLOY = "deploy"


class Verdict(str, Enum):
    ALLOW = "allow"        # ✓
    DENY = "deny"          # ✗（必附 error_code）
    QUEUE = "queue"        # Q（佇列待確認）
    SEQUENCE = "sequence"  # →（強制順序，如先 pause 再 audit）


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    next_state: TaskRuntimeState | None = None
    error_code: str = ""
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict in (Verdict.ALLOW, Verdict.SEQUENCE)


# ── 衝突錯誤碼（寫死，前後端共用） ─────────────────────────────
ERR_RESUME_WHILE_RUNNING = "ERR_RESUME_WHILE_RUNNING"
ERR_DEPLOY_BEFORE_COMPILE = "ERR_DEPLOY_BEFORE_COMPILE"
ERR_DUPLICATE_AUDIT = "ERR_DUPLICATE_AUDIT"
ERR_RESUME_BEFORE_AUDIT_END = "ERR_RESUME_BEFORE_AUDIT_END"
ERR_SNAPSHOT_FROZEN_REFRESH = "ERR_SNAPSHOT_FROZEN_REFRESH"   # 審計中凍結快照
ERR_PLUGIN_SET_FROZEN = "ERR_PLUGIN_SET_FROZEN"               # 審計中凍結插件集合
ERR_AUDIT_WHILE_COMPILING = "ERR_AUDIT_WHILE_COMPILING"       # §9.1：簡化實作一律拒絕
ERR_DUPLICATE_REFRESH = "ERR_DUPLICATE_REFRESH"
ERR_DUPLICATE_COMPILE = "ERR_DUPLICATE_COMPILE"
ERR_RESUME_WHILE_REFRESHING = "ERR_RESUME_WHILE_REFRESHING"
ERR_DEPLOY_WHILE_REFRESHING = "ERR_DEPLOY_WHILE_REFRESHING"
ERR_AWAITING_CONFIRMATION = "ERR_AWAITING_CONFIRMATION"       # 須先確認衝突處理
ERR_AUDIT_WHILE_COMPILING_NOTE = "編譯結束後可審計包含編譯記錄的完整軌跡（§9.1）"

_S = TaskRuntimeState
_A = TaskAction

_ALLOW = Decision(Verdict.ALLOW)


def _deny(code: str, note: str = "") -> Decision:
    return Decision(Verdict.DENY, error_code=code, note=note)


def _queue(note: str = "") -> Decision:
    return Decision(Verdict.QUEUE, note=note)


# ── 轉換矩陣（對照 TODO §9 表格逐行落碼） ──────────────────────
# key: (當前狀態, 請求動作)
_MATRIX: dict[tuple[TaskRuntimeState, TaskAction], Decision] = {
    # running
    (_S.RUNNING, _A.PAUSE): Decision(Verdict.ALLOW, _S.PAUSED, note="等 inflight 自然完成，禁止強制 abort"),
    (_S.RUNNING, _A.AUDIT): Decision(Verdict.SEQUENCE, _S.PAUSED, note="先 pause 再 audit（§1.3）"),
    (_S.RUNNING, _A.RESUME): _deny(ERR_RESUME_WHILE_RUNNING),
    (_S.RUNNING, _A.L0_REFRESH): _queue("預設佇列（策略可配）"),
    (_S.RUNNING, _A.PLUGIN_TOGGLE): Decision(Verdict.ALLOW, note="不中斷 inflight；UI 鎖定避免重複提交"),
    (_S.RUNNING, _A.COMPILE): Decision(Verdict.ALLOW, _S.COMPILING),
    (_S.RUNNING, _A.DEPLOY): _deny(ERR_DEPLOY_BEFORE_COMPILE),
    # paused
    (_S.PAUSED, _A.AUDIT): Decision(Verdict.ALLOW, _S.AUDITING),
    (_S.PAUSED, _A.RESUME): Decision(Verdict.ALLOW, _S.RUNNING, note="須先校驗快照版本（§1.5）"),
    (_S.PAUSED, _A.L0_REFRESH): _queue("恢復前須確認版本"),
    (_S.PAUSED, _A.PLUGIN_TOGGLE): _ALLOW,
    (_S.PAUSED, _A.COMPILE): Decision(Verdict.ALLOW, _S.COMPILING),
    (_S.PAUSED, _A.DEPLOY): Decision(Verdict.ALLOW, note="僅當已待部署（§9）"),
    # auditing
    (_S.AUDITING, _A.AUDIT): _deny(ERR_DUPLICATE_AUDIT),
    (_S.AUDITING, _A.RESUME): _deny(ERR_RESUME_BEFORE_AUDIT_END),
    (_S.AUDITING, _A.L0_REFRESH): _deny(ERR_SNAPSHOT_FROZEN_REFRESH, "審計中禁止 L0 刷新（§9.1）"),
    (_S.AUDITING, _A.PLUGIN_TOGGLE): _deny(ERR_PLUGIN_SET_FROZEN, "審計中凍結插件集合（§9.1）"),
    (_S.AUDITING, _A.COMPILE): _deny(ERR_AUDIT_WHILE_COMPILING, "審計中禁止編譯"),
    (_S.AUDITING, _A.DEPLOY): _deny(ERR_AUDIT_WHILE_COMPILING, "審計中禁止部署"),
    # l0_refreshing
    (_S.L0_REFRESHING, _A.PAUSE): Decision(Verdict.ALLOW, _S.PAUSED, note="可暫停任務"),
    (_S.L0_REFRESHING, _A.AUDIT): _queue("刷新完成後自動進入 paused → auditing（§9）"),
    (_S.L0_REFRESHING, _A.RESUME): _deny(ERR_RESUME_WHILE_REFRESHING),
    (_S.L0_REFRESHING, _A.L0_REFRESH): _deny(ERR_DUPLICATE_REFRESH),
    (_S.L0_REFRESHING, _A.PLUGIN_TOGGLE): _queue(),
    (_S.L0_REFRESHING, _A.COMPILE): _queue(),
    (_S.L0_REFRESHING, _A.DEPLOY): _deny(ERR_DEPLOY_WHILE_REFRESHING),
    # plugin_degraded
    (_S.PLUGIN_DEGRADED, _A.PAUSE): Decision(Verdict.ALLOW, _S.PAUSED),
    (_S.PLUGIN_DEGRADED, _A.AUDIT): Decision(Verdict.ALLOW, _S.AUDITING, note="範圍含插件呼叫記錄（§6.3）"),
    (_S.PLUGIN_DEGRADED, _A.RESUME): Decision(Verdict.ALLOW, _S.RUNNING, note="恢復時不自動重試失敗插件（§9.1）"),
    (_S.PLUGIN_DEGRADED, _A.L0_REFRESH): _ALLOW,
    (_S.PLUGIN_DEGRADED, _A.PLUGIN_TOGGLE): Decision(Verdict.ALLOW, note="可顯式重試啟用"),
    (_S.PLUGIN_DEGRADED, _A.COMPILE): Decision(Verdict.ALLOW, _S.COMPILING),
    (_S.PLUGIN_DEGRADED, _A.DEPLOY): Decision(Verdict.ALLOW, note="依策略（§9）"),
    # compiling / sandboxing
    (_S.COMPILING, _A.PAUSE): Decision(Verdict.ALLOW, _S.PAUSED),
    (_S.COMPILING, _A.AUDIT): _deny(ERR_AUDIT_WHILE_COMPILING, ERR_AUDIT_WHILE_COMPILING_NOTE),
    (_S.COMPILING, _A.RESUME): _deny(ERR_RESUME_BEFORE_AUDIT_END, "編譯中不可恢復"),
    (_S.COMPILING, _A.L0_REFRESH): _queue(),
    (_S.COMPILING, _A.PLUGIN_TOGGLE): _queue(),
    (_S.COMPILING, _A.COMPILE): _deny(ERR_DUPLICATE_COMPILE),
    (_S.COMPILING, _A.DEPLOY): _deny(ERR_DEPLOY_BEFORE_COMPILE, "沙盒未通過不得部署"),
    (_S.SANDBOXING, _A.PAUSE): Decision(Verdict.ALLOW, _S.PAUSED),
    (_S.SANDBOXING, _A.AUDIT): _deny(ERR_AUDIT_WHILE_COMPILING, ERR_AUDIT_WHILE_COMPILING_NOTE),
    (_S.SANDBOXING, _A.RESUME): _deny(ERR_RESUME_BEFORE_AUDIT_END, "沙盒驗證中不可恢復"),
    (_S.SANDBOXING, _A.L0_REFRESH): _queue(),
    (_S.SANDBOXING, _A.PLUGIN_TOGGLE): _queue(),
    (_S.SANDBOXING, _A.COMPILE): _deny(ERR_DUPLICATE_COMPILE),
    (_S.SANDBOXING, _A.DEPLOY): _deny(ERR_DEPLOY_BEFORE_COMPILE, "沙盒未通過不得部署"),
    # awaiting_deploy
    (_S.AWAITING_DEPLOY, _A.PAUSE): Decision(
        Verdict.ALLOW, _S.PAUSED,
        note="暫停的是任務生命週期；部署審批流程獨立，不受影響（§9.1 寫死）",
    ),
    (_S.AWAITING_DEPLOY, _A.AUDIT): Decision(Verdict.ALLOW, _S.AUDITING),
    (_S.AWAITING_DEPLOY, _A.RESUME): Decision(Verdict.ALLOW, _S.RUNNING),
    (_S.AWAITING_DEPLOY, _A.L0_REFRESH): _queue(),
    (_S.AWAITING_DEPLOY, _A.PLUGIN_TOGGLE): _ALLOW,
    (_S.AWAITING_DEPLOY, _A.COMPILE): Decision(Verdict.ALLOW, _S.COMPILING, note="新編譯替換待部署"),
    (_S.AWAITING_DEPLOY, _A.DEPLOY): Decision(Verdict.ALLOW, note="顯式部署（§8.2）"),
    # awaiting_confirmation（快照衝突待確認，§1.5／§9.1）
    (_S.AWAITING_CONFIRMATION, _A.AUDIT): _deny(ERR_AWAITING_CONFIRMATION, "此狀態禁止審計"),
    (_S.AWAITING_CONFIRMATION, _A.RESUME): _queue("須先確認衝突處理（重綁／放棄）"),
    (_S.AWAITING_CONFIRMATION, _A.L0_REFRESH): _queue(),
    (_S.AWAITING_CONFIRMATION, _A.PLUGIN_TOGGLE): _queue(),
    (_S.AWAITING_CONFIRMATION, _A.COMPILE): _queue(),
    (_S.AWAITING_CONFIRMATION, _A.DEPLOY): _deny(ERR_AWAITING_CONFIRMATION, "此狀態禁止部署"),
}


def evaluate(state: TaskRuntimeState | str, action: TaskAction | str) -> Decision:
    """查表；未定義組合（如同態自轉 pause@paused）視為 no-op 允許，不轉態。"""
    state = TaskRuntimeState(state)
    action = TaskAction(action)
    decision = _MATRIX.get((state, action))
    if decision is None:
        return Decision(Verdict.ALLOW, None, note="no-op（同態或未列舉組合）")
    return decision


def transition(state: TaskRuntimeState | str, action: TaskAction | str) -> TaskRuntimeState:
    """對 ALLOW／SEQUENCE 回傳下一狀態；DENY／QUEUE 回傳原狀態（不改變凍結快照）。"""
    state = TaskRuntimeState(state)
    decision = evaluate(state, action)
    if decision.ok and decision.next_state is not None:
        return decision.next_state
    return state


def denied_pairs() -> list[tuple[TaskRuntimeState, TaskAction, str]]:
    """供測試列舉所有 ✗ 路徑及其錯誤碼（§9.2 驗收）。"""
    return [
        (state, action, d.error_code)
        for (state, action), d in _MATRIX.items()
        if d.verdict is Verdict.DENY
    ]


def queued_pairs() -> list[tuple[TaskRuntimeState, TaskAction]]:
    """供測試列舉所有 Q 路徑（§9.2 驗收）。"""
    return [
        (state, action)
        for (state, action), d in _MATRIX.items()
        if d.verdict is Verdict.QUEUE
    ]
