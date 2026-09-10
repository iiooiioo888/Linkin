# -*- coding: utf-8 -*-
"""Write remaining follow-up artifacts for C-PERF-001 / C-UI-001 / C-UI-002."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent

TASK_STATE_MATRIX_TS = r"""/**
 * 任務狀態矩陣（TODO §9／C-UI-002）。
 * 與 backend/company/task_state_machine.py 對齊；UI 按鈕可用性必須以此為準，
 * 禁止前端自行放行後端會拒絕的組合。
 */
export const TASK_RUNTIME_STATES = [
  'running',
  'paused',
  'auditing',
  'l0_refreshing',
  'plugin_degraded',
  'compiling',
  'sandboxing',
  'awaiting_deploy',
  'awaiting_confirmation',
] as const;

export type TaskRuntimeState = (typeof TASK_RUNTIME_STATES)[number];

export const TASK_ACTIONS = [
  'pause',
  'audit',
  'resume',
  'l0_refresh',
  'plugin_toggle',
  'compile',
  'deploy',
] as const;

export type TaskAction = (typeof TASK_ACTIONS)[number];

export type Verdict = 'allow' | 'deny' | 'queue' | 'sequence';

export type MatrixDecision = {
  verdict: Verdict;
  nextState?: TaskRuntimeState | null;
  errorCode?: string;
  note?: string;
};

const MATRIX: Record<string, MatrixDecision> = {
  'running|pause': { verdict: 'allow', nextState: 'paused' },
  'running|audit': { verdict: 'sequence', nextState: 'paused', note: '先 pause 再 audit' },
  'running|resume': { verdict: 'deny', errorCode: 'ERR_RESUME_WHILE_RUNNING' },
  'running|l0_refresh': { verdict: 'queue' },
  'running|plugin_toggle': { verdict: 'allow' },
  'running|compile': { verdict: 'allow', nextState: 'compiling' },
  'running|deploy': { verdict: 'deny', errorCode: 'ERR_DEPLOY_BEFORE_COMPILE' },
  'paused|audit': { verdict: 'allow', nextState: 'auditing' },
  'paused|resume': { verdict: 'allow', nextState: 'running' },
  'paused|l0_refresh': { verdict: 'queue' },
  'paused|plugin_toggle': { verdict: 'allow' },
  'paused|compile': { verdict: 'allow', nextState: 'compiling' },
  'paused|deploy': { verdict: 'allow' },
  'auditing|audit': { verdict: 'deny', errorCode: 'ERR_DUPLICATE_AUDIT' },
  'auditing|resume': { verdict: 'deny', errorCode: 'ERR_RESUME_BEFORE_AUDIT_END' },
  'auditing|l0_refresh': { verdict: 'deny', errorCode: 'ERR_SNAPSHOT_FROZEN_REFRESH' },
  'auditing|plugin_toggle': { verdict: 'deny', errorCode: 'ERR_PLUGIN_SET_FROZEN' },
  'auditing|compile': { verdict: 'deny', errorCode: 'ERR_AUDIT_WHILE_COMPILING' },
  'auditing|deploy': { verdict: 'deny', errorCode: 'ERR_AUDIT_WHILE_COMPILING' },
  'l0_refreshing|pause': { verdict: 'allow', nextState: 'paused' },
  'l0_refreshing|audit': { verdict: 'queue' },
  'l0_refreshing|resume': { verdict: 'deny', errorCode: 'ERR_RESUME_WHILE_REFRESHING' },
  'l0_refreshing|l0_refresh': { verdict: 'deny', errorCode: 'ERR_DUPLICATE_REFRESH' },
  'l0_refreshing|plugin_toggle': { verdict: 'queue' },
  'l0_refreshing|compile': { verdict: 'queue' },
  'l0_refreshing|deploy': { verdict: 'deny', errorCode: 'ERR_DEPLOY_WHILE_REFRESHING' },
  'plugin_degraded|pause': { verdict: 'allow', nextState: 'paused' },
  'plugin_degraded|audit': { verdict: 'allow', nextState: 'auditing' },
  'plugin_degraded|resume': { verdict: 'allow', nextState: 'running' },
  'plugin_degraded|l0_refresh': { verdict: 'allow' },
  'plugin_degraded|plugin_toggle': { verdict: 'allow' },
  'plugin_degraded|compile': { verdict: 'allow', nextState: 'compiling' },
  'plugin_degraded|deploy': { verdict: 'allow' },
  'compiling|pause': { verdict: 'allow', nextState: 'paused' },
  'compiling|audit': { verdict: 'deny', errorCode: 'ERR_AUDIT_WHILE_COMPILING' },
  'compiling|resume': { verdict: 'deny', errorCode: 'ERR_RESUME_BEFORE_AUDIT_END' },
  'compiling|l0_refresh': { verdict: 'queue' },
  'compiling|plugin_toggle': { verdict: 'queue' },
  'compiling|compile': { verdict: 'deny', errorCode: 'ERR_DUPLICATE_COMPILE' },
  'compiling|deploy': { verdict: 'deny', errorCode: 'ERR_DEPLOY_BEFORE_COMPILE' },
  'sandboxing|pause': { verdict: 'allow', nextState: 'paused' },
  'sandboxing|audit': { verdict: 'deny', errorCode: 'ERR_AUDIT_WHILE_COMPILING' },
  'sandboxing|resume': { verdict: 'deny', errorCode: 'ERR_RESUME_BEFORE_AUDIT_END' },
  'sandboxing|l0_refresh': { verdict: 'queue' },
  'sandboxing|plugin_toggle': { verdict: 'queue' },
  'sandboxing|compile': { verdict: 'deny', errorCode: 'ERR_DUPLICATE_COMPILE' },
  'sandboxing|deploy': { verdict: 'deny', errorCode: 'ERR_DEPLOY_BEFORE_COMPILE' },
  'awaiting_deploy|pause': { verdict: 'allow', nextState: 'paused' },
  'awaiting_deploy|audit': { verdict: 'allow', nextState: 'auditing' },
  'awaiting_deploy|resume': { verdict: 'allow', nextState: 'running' },
  'awaiting_deploy|l0_refresh': { verdict: 'queue' },
  'awaiting_deploy|plugin_toggle': { verdict: 'allow' },
  'awaiting_deploy|compile': { verdict: 'allow', nextState: 'compiling' },
  'awaiting_deploy|deploy': { verdict: 'allow' },
  'awaiting_confirmation|audit': { verdict: 'deny', errorCode: 'ERR_AWAITING_CONFIRMATION' },
  'awaiting_confirmation|resume': { verdict: 'queue' },
  'awaiting_confirmation|l0_refresh': { verdict: 'queue' },
  'awaiting_confirmation|plugin_toggle': { verdict: 'queue' },
  'awaiting_confirmation|compile': { verdict: 'queue' },
  'awaiting_confirmation|deploy': { verdict: 'deny', errorCode: 'ERR_AWAITING_CONFIRMATION' },
};

export function evaluate(state: TaskRuntimeState | string, action: TaskAction | string): MatrixDecision {
  const key = state + '|' + action;
  return MATRIX[key] ?? { verdict: 'allow', note: 'no-op' };
}

/** DENY → 禁用；其餘（含 QUEUE）可點擊提交。 */
export function buttonEnabled(state: TaskRuntimeState | string, action: TaskAction | string): boolean {
  return evaluate(state, action).verdict !== 'deny';
}

/**
 * 由任務進度推估運行時狀態（後端尚未下發 runtime_state 時的相容映射）。
 * 有明確 runtime_state 時一律優先。
 */
export function inferRuntimeState(task: {
  status?: string;
  resumable?: boolean;
  runtime_state?: string | null;
  phase?: string;
}): TaskRuntimeState {
  const explicit = String(task.runtime_state || '').trim();
  if ((TASK_RUNTIME_STATES as readonly string[]).includes(explicit)) {
    return explicit as TaskRuntimeState;
  }
  const status = String(task.status || '').toLowerCase();
  const phase = String(task.phase || '').toLowerCase();
  if (phase.includes('audit') || status === 'auditing') return 'auditing';
  if (phase.includes('compil') || status === 'compiling') return 'compiling';
  if (phase.includes('sandbox')) return 'sandboxing';
  if (phase.includes('refresh') || status === 'l0_refreshing') return 'l0_refreshing';
  if (status === 'running' || status === 'pending') return 'running';
  if (task.resumable || status === 'interrupted' || status === 'paused') return 'paused';
  if (status === 'completed' || status === 'failed' || status === 'cancelled') return 'paused';
  return 'running';
}
"""

CONTRACT_TESTS_APPEND = r'''

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
'''


def write_task_state_matrix() -> None:
    path = ROOT / "frontend" / "src" / "lib" / "taskStateMatrix.ts"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TASK_STATE_MATRIX_TS, encoding="utf-8")
    print("wrote", path)


def append_contract_tests() -> None:
    path = ROOT / "backend" / "tests" / "test_contracts.py"
    text = path.read_text(encoding="utf-8")
    if "test_contract_c_perf_001_stubbed_clock_budgets" in text:
        print("contract tests already present")
        return
    path.write_text(text.rstrip() + "\n" + CONTRACT_TESTS_APPEND, encoding="utf-8")
    print("appended contract tests")


def patch_monitor_section() -> None:
    path = ROOT / "frontend" / "src" / "components" / "ChatMonitorCards.tsx"
    text = path.read_text(encoding="utf-8")
    if "defaultCollapsed" in text:
        print("MonitorSection already collapsible")
        return
    old = '''export function MonitorSection({
  title,
  hint,
  badge,
  children,
  scroll = false,
  maxHeight,
}: {
  title: string;
  hint?: string;
  badge?: string;
  children: ReactNode;
  scroll?: boolean;
  maxHeight?: string;
}) {
  return (
    <section
      className="apple-card"
      style={scroll && maxHeight ? { maxHeight } : undefined}
    >
      <div className="apple-card__head">
        <div className="flex min-w-0 items-center gap-2">
          <h4 className="apple-title">{title}</h4>
          {badge && (
            <span
              className={`rounded-md px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${
                badge === 'LIVE'
                  ? 'bg-[#34C759]/15 text-[#34C759]'
                  : 'bg-white/5 text-[#8E8E93]'
              }`}
            >
              {badge}
            </span>
          )}
        </div>
        {hint && <span className="shrink-0 text-[10px] font-normal text-[#636366]">{hint}</span>}
      </div>
      <div className={`apple-card__body ${scroll ? '' : 'apple-card__body--static'}`}>
        {children}
      </div>
    </section>
  );
}'''
    new = '''export function MonitorSection({
  title,
  hint,
  badge,
  children,
  scroll = false,
  maxHeight,
  defaultCollapsed = false,
}: {
  title: string;
  hint?: string;
  badge?: string;
  children: ReactNode;
  scroll?: boolean;
  maxHeight?: string;
  /** C-UI-001：預設折疊防過載 */
  defaultCollapsed?: boolean;
}) {
  const [open, setOpen] = useState(!defaultCollapsed);
  return (
    <section
      className="apple-card"
      style={scroll && maxHeight && open ? { maxHeight } : undefined}
    >
      <button
        type="button"
        className="apple-card__head w-full cursor-pointer text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-2">
          <h4 className="apple-title">{title}</h4>
          {badge && (
            <span
              className={`rounded-md px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${
                badge === 'LIVE'
                  ? 'bg-[#34C759]/15 text-[#34C759]'
                  : 'bg-white/5 text-[#8E8E93]'
              }`}
            >
              {badge}
            </span>
          )}
        </div>
        <span className="shrink-0 text-[10px] font-normal text-[#636366]">
          {hint ? `${hint} · ` : ''}{open ? '收合' : '展開'}
        </span>
      </button>
      {open ? (
        <div className={`apple-card__body ${scroll ? '' : 'apple-card__body--static'}`}>
          {children}
        </div>
      ) : null}
    </section>
  );
}'''
    if old not in text:
        raise SystemExit("MonitorSection block not found")
    if "import { useState" not in text and "useState" not in text:
        text = text.replace(
            "import type { ReactNode } from 'react';",
            "import { useState, type ReactNode } from 'react';",
        )
    elif "import type { ReactNode } from 'react';" in text:
        text = text.replace(
            "import type { ReactNode } from 'react';",
            "import { useState, type ReactNode } from 'react';",
        )
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("patched MonitorSection")


def patch_chat_task_monitor() -> None:
    path = ROOT / "frontend" / "src" / "components" / "ChatTaskMonitor.tsx"
    text = path.read_text(encoding="utf-8")
    if "buttonEnabled" in text and "inferRuntimeState" in text:
        print("ChatTaskMonitor already wired")
        return

    if "from '../lib/taskStateMatrix'" not in text:
        text = text.replace(
            "import { formatDurationCompact, taskEta } from '../lib/taskTiming';",
            "import { formatDurationCompact, taskEta } from '../lib/taskTiming';\n"
            "import { buttonEnabled, inferRuntimeState } from '../lib/taskStateMatrix';",
        )

    # inject runtime state + gated buttons after const blockers
    needle = "  const blockers = pending.filter((p) => !p.resolved);\n\n  return ("
    inject = """  const blockers = pending.filter((p) => !p.resolved);
  const runtimeState = inferRuntimeState({
    status: task.status,
    resumable: task.resumable,
    runtime_state: (task as { runtime_state?: string }).runtime_state,
    phase: task.phase,
  });
  const canPause = buttonEnabled(runtimeState, 'pause') && Boolean(onPause);
  const canResume = buttonEnabled(runtimeState, 'resume') && Boolean(onResume) && Boolean(task.resumable);
  const spentPct = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : 0;
  const primarySeat = roleRows.find((r) => r.status === 'busy') || roleRows[0];

  return ("""
    if needle not in text:
        raise SystemExit("blockers needle missing")
    text = text.replace(needle, inject)

    # replace action buttons block
    old_acts = """        <div className="ws-side-acts">
          {running && onPause && (
            <button type="button" className="ws-btn ws-btn-danger" onClick={onPause}>
              暫停
            </button>
          )}
          {task.resumable && !running && !blockers.length && onResume && (
            <button type="button" className="ws-btn ws-btn-primary" onClick={onResume}>
              續跑
            </button>
          )}"""
    new_acts = """        <div className="ws-side-acts">
          {canPause && running && (
            <button type="button" className="ws-btn ws-btn-danger" onClick={onPause} data-matrix-action="pause">
              暫停
            </button>
          )}
          {canResume && !running && !blockers.length && (
            <button type="button" className="ws-btn ws-btn-primary" onClick={onResume} data-matrix-action="resume">
              續跑
            </button>
          )}"""
    if old_acts not in text:
        raise SystemExit("action buttons block missing")
    text = text.replace(old_acts, new_acts)

    # C-UI-001: compact HUD after kpi + collapse heavy sections
    old_kpi = """        <div className="ws-side-kpi">
          <div>
            <span>耗時</span>
            <strong>{eta ? formatDurationCompact(eta.elapsedSec) : '—'}</strong>
          </div>
          <div>
            <span>階段</span>
            <strong>{running ? '執行中' : task.status}</strong>
          </div>
        </div>

        <MonitorSection title="啟用角色" hint={`${enabledN}/${roleRows.length || 0}`}>"""
    new_kpi = """        <div className="ws-side-kpi" data-testid="runtime-hud-compact">
          <div>
            <span>席位</span>
            <strong>{primarySeat?.name || '—'}</strong>
          </div>
          <div>
            <span>動作</span>
            <strong>{phaseLabel}</strong>
          </div>
          <div>
            <span>預算</span>
            <strong>{spentPct}%</strong>
          </div>
        </div>
        <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-white/10" title="任務預算進度">
          <i className="block h-full rounded-full bg-[#0A84FF]" style={{ width: `${spentPct}%` }} />
        </div>
        <p className="mb-2 text-[10px] text-[#636366]">
          狀態 {runtimeState} · 耗時 {eta ? formatDurationCompact(eta.elapsedSec) : '—'}
        </p>

        <MonitorSection title="啟用角色" hint={`${enabledN}/${roleRows.length || 0}`} defaultCollapsed>"""
    if old_kpi not in text:
        raise SystemExit("kpi block missing")
    text = text.replace(old_kpi, new_kpi)

    text = text.replace(
        '<MonitorSection title="外部整合" hint="召回／Agent／設計">',
        '<MonitorSection title="外部整合" hint="召回／Agent／設計" defaultCollapsed>',
    )
    # L4 需求審計門票分數：預設折疊，且不佔常駐 HUD 分數槽（C-UI-001）
    text = text.replace(
        "<MonitorSection title=\"審計\" hint={ticket ? ticketStatusLabel(ticket.status) : '尚無門票'}>",
        "<MonitorSection title=\"需求審計門票\" hint={ticket ? ticketStatusLabel(ticket.status) : '尚無門票'} defaultCollapsed>",
    )
    text = text.replace(
        '<MonitorSection title="AI 計費" hint={model || \'模型用量\'}>',
        '<MonitorSection title="AI 計費" hint={model || \'模型用量\'} defaultCollapsed>',
    )
    text = text.replace(
        """        <MonitorSection
          title="Docker 計費"
          hint={dockerRate > 0 ? `${fmtUsd(dockerRate)}/h` : '容器按時'}
        >""",
        """        <MonitorSection
          title="Docker 計費"
          hint={dockerRate > 0 ? `${fmtUsd(dockerRate)}/h` : '容器按時'}
          defaultCollapsed
        >""",
    )

    path.write_text(text, encoding="utf-8")
    print("patched ChatTaskMonitor")


def patch_runtime_md() -> None:
    path = ROOT / "docs" / "contracts" / "runtime.md"
    text = path.read_text(encoding="utf-8")
    text2 = text
    text2 = text2.replace(
        "- **驗證**: e2e::core-flow.spec.ts（規劃中擴充）＋ IntegrationsStrip／ChatTaskMonitor 不渲染審計分數槽\n"
        "- **狀態**: 🚧 進行中（IntegrationsPanel／Strip／LiveBoard／StatusBar／L0 來源列已落地；常駐狀態列完整折疊待 §3）",
        "- **驗證**: ChatTaskMonitor 預設折疊＋compact HUD（席位／動作／預算）；需求審計門票分數不佔常駐槽\n"
        "- **狀態**: ✅ 已實現（compact HUD＋MonitorSection defaultCollapsed；完整 e2e 仍可擴充）",
    )
    text2 = text2.replace(
        "- **驗證**: e2e::state-matrix-buttons（規劃中）\n"
        "- **狀態**: ❌ 未實現",
        "- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_ui_002_button_enabled_matches_deny_matrix "
        "＋ frontend/src/lib/taskStateMatrix.ts＋GET /runtime/state-matrix\n"
        "- **狀態**: ✅ 已實現",
    )
    text2 = text2.replace(
        "- **驗證**: pytest::test_perf_budget_stubbed_clock（規劃中）\n"
        "- **狀態**: ❌ 未實現",
        "- **驗證**: pytest::backend/tests/test_contracts.py::test_contract_c_perf_001_stubbed_clock_budgets"
        "（`backend/core/perf_budget.py`）\n"
        "- **狀態**: ✅ 已實現",
    )
    if text2 == text:
        print("runtime.md: no changes (patterns may already updated)")
    else:
        path.write_text(text2, encoding="utf-8")
        print("runtime.md updated")


def patch_types() -> None:
    path = ROOT / "frontend" / "src" / "types.ts"
    text = path.read_text(encoding="utf-8")
    if "runtime_state?" in text:
        print("types already have runtime_state")
        return
    needle = "  resumable?: boolean;\n"
    insert = "  resumable?: boolean;\n  /** TODO §9 單任務運行時狀態（C-UI-002） */\n  runtime_state?: string;\n"
    if needle not in text:
        raise SystemExit("resumable needle missing")
    path.write_text(text.replace(needle, insert, 1), encoding="utf-8")
    print("types: runtime_state added")


if __name__ == "__main__":
    write_task_state_matrix()
    append_contract_tests()
    patch_monitor_section()
    patch_chat_task_monitor()
    patch_types()
    patch_runtime_md()
    print("ALL_OK")
