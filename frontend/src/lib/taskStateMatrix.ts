/**
 * 任務狀態矩陣（TODO §9／C-UI-002）。
 *
 * **MATRIX 由後端生成，請勿手改**：
 *   `cd /opt/linkin && PYTHONPATH=/opt/linkin .venv/bin/python -m backend.scripts.export_task_state_matrix`
 * 來源單一真相＝`backend/company/task_state_machine.py::export_matrix`。
 *
 * 為何改為生成：先前本檔手抄矩陣，缺了 15 個 `*|l0_refresh` 格子，而
 * `evaluate()` 對查不到的鍵兜底回 `allow`，使 UI 放行後端必然拒絕的組合
 * （例如 `auditing|l0_refresh` 後端為 DENY `ERR_SNAPSHOT_FROZEN_REFRESH`，
 * 前端卻按 allow 顯示可按）——違反 §3.4／C-UI-002「禁止前端自行放行後端
 * 會拒絕的組合」。契約測試 `C-UI-002` 會擋住再次漂移。
 */

/* GENERATED:START — 由 backend/scripts/export_task_state_matrix.py 產生，請勿手改 */
export const TASK_STATE_MATRIX_SCHEMA = 'todo-§9-v1' as const;

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

export const TASK_ACTIONS = [
  'pause',
  'audit',
  'resume',
  'l0_refresh',
  'plugin_toggle',
  'compile',
  'deploy',
] as const;

export type TaskRuntimeState = (typeof TASK_RUNTIME_STATES)[number];
export type TaskAction = (typeof TASK_ACTIONS)[number];

export type Verdict = 'allow' | 'deny' | 'queue' | 'sequence';

export type MatrixDecision = {
  verdict: Verdict;
  nextState?: TaskRuntimeState | null;
  errorCode?: string;
  note?: string;
  buttonEnabled: boolean;
};

/** 後端 §9 矩陣完整匯出（鍵＝`state|action`）。 */
export const MATRIX: Record<string, MatrixDecision> = {
  'auditing|audit': { verdict: 'deny', nextState: null, errorCode: 'ERR_DUPLICATE_AUDIT', buttonEnabled: false },
  'auditing|compile': { verdict: 'deny', nextState: null, errorCode: 'ERR_AUDIT_WHILE_COMPILING', note: '審計中禁止編譯', buttonEnabled: false },
  'auditing|deploy': { verdict: 'deny', nextState: null, errorCode: 'ERR_AUDIT_WHILE_COMPILING', note: '審計中禁止部署', buttonEnabled: false },
  'auditing|l0_refresh': { verdict: 'deny', nextState: null, errorCode: 'ERR_SNAPSHOT_FROZEN_REFRESH', note: '審計中禁止 L0 刷新（§9.1）', buttonEnabled: false },
  'auditing|plugin_toggle': { verdict: 'deny', nextState: null, errorCode: 'ERR_PLUGIN_SET_FROZEN', note: '審計中凍結插件集合（§9.1）', buttonEnabled: false },
  'auditing|resume': { verdict: 'deny', nextState: null, errorCode: 'ERR_RESUME_BEFORE_AUDIT_END', buttonEnabled: false },
  'awaiting_confirmation|audit': { verdict: 'deny', nextState: null, errorCode: 'ERR_AWAITING_CONFIRMATION', note: '此狀態禁止審計', buttonEnabled: false },
  'awaiting_confirmation|compile': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'awaiting_confirmation|deploy': { verdict: 'deny', nextState: null, errorCode: 'ERR_AWAITING_CONFIRMATION', note: '此狀態禁止部署', buttonEnabled: false },
  'awaiting_confirmation|l0_refresh': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'awaiting_confirmation|plugin_toggle': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'awaiting_confirmation|resume': { verdict: 'queue', nextState: null, errorCode: '', note: '須先確認衝突處理（重綁／放棄）', buttonEnabled: true },
  'awaiting_deploy|audit': { verdict: 'allow', nextState: 'auditing', errorCode: '', buttonEnabled: true },
  'awaiting_deploy|compile': { verdict: 'allow', nextState: 'compiling', errorCode: '', note: '新編譯替換待部署', buttonEnabled: true },
  'awaiting_deploy|deploy': { verdict: 'allow', nextState: null, errorCode: '', note: '顯式部署（§8.2）', buttonEnabled: true },
  'awaiting_deploy|l0_refresh': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'awaiting_deploy|pause': { verdict: 'allow', nextState: 'paused', errorCode: '', note: '暫停的是任務生命週期；部署審批流程獨立，不受影響（§9.1 寫死）', buttonEnabled: true },
  'awaiting_deploy|plugin_toggle': { verdict: 'allow', nextState: null, errorCode: '', buttonEnabled: true },
  'awaiting_deploy|resume': { verdict: 'allow', nextState: 'running', errorCode: '', buttonEnabled: true },
  'compiling|audit': { verdict: 'deny', nextState: null, errorCode: 'ERR_AUDIT_WHILE_COMPILING', note: '編譯結束後可審計包含編譯記錄的完整軌跡（§9.1）', buttonEnabled: false },
  'compiling|compile': { verdict: 'deny', nextState: null, errorCode: 'ERR_DUPLICATE_COMPILE', buttonEnabled: false },
  'compiling|deploy': { verdict: 'deny', nextState: null, errorCode: 'ERR_DEPLOY_BEFORE_COMPILE', note: '沙盒未通過不得部署', buttonEnabled: false },
  'compiling|l0_refresh': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'compiling|pause': { verdict: 'allow', nextState: 'paused', errorCode: '', buttonEnabled: true },
  'compiling|plugin_toggle': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'compiling|resume': { verdict: 'deny', nextState: null, errorCode: 'ERR_RESUME_BEFORE_AUDIT_END', note: '編譯中不可恢復', buttonEnabled: false },
  'l0_refreshing|audit': { verdict: 'queue', nextState: null, errorCode: '', note: '刷新完成後自動進入 paused → auditing（§9）', buttonEnabled: true },
  'l0_refreshing|compile': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'l0_refreshing|deploy': { verdict: 'deny', nextState: null, errorCode: 'ERR_DEPLOY_WHILE_REFRESHING', buttonEnabled: false },
  'l0_refreshing|l0_refresh': { verdict: 'deny', nextState: null, errorCode: 'ERR_DUPLICATE_REFRESH', buttonEnabled: false },
  'l0_refreshing|pause': { verdict: 'allow', nextState: 'paused', errorCode: '', note: '可暫停任務', buttonEnabled: true },
  'l0_refreshing|plugin_toggle': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'l0_refreshing|resume': { verdict: 'deny', nextState: null, errorCode: 'ERR_RESUME_WHILE_REFRESHING', buttonEnabled: false },
  'paused|audit': { verdict: 'allow', nextState: 'auditing', errorCode: '', buttonEnabled: true },
  'paused|compile': { verdict: 'allow', nextState: 'compiling', errorCode: '', buttonEnabled: true },
  'paused|deploy': { verdict: 'allow', nextState: null, errorCode: '', note: '僅當已待部署（§9）', buttonEnabled: true },
  'paused|l0_refresh': { verdict: 'queue', nextState: null, errorCode: '', note: '恢復前須確認版本', buttonEnabled: true },
  'paused|plugin_toggle': { verdict: 'allow', nextState: null, errorCode: '', buttonEnabled: true },
  'paused|resume': { verdict: 'allow', nextState: 'running', errorCode: '', note: '須先校驗快照版本（§1.5）', buttonEnabled: true },
  'plugin_degraded|audit': { verdict: 'allow', nextState: 'auditing', errorCode: '', note: '範圍含插件呼叫記錄（§6.3）', buttonEnabled: true },
  'plugin_degraded|compile': { verdict: 'allow', nextState: 'compiling', errorCode: '', buttonEnabled: true },
  'plugin_degraded|deploy': { verdict: 'allow', nextState: null, errorCode: '', note: '依策略（§9）', buttonEnabled: true },
  'plugin_degraded|l0_refresh': { verdict: 'allow', nextState: null, errorCode: '', buttonEnabled: true },
  'plugin_degraded|pause': { verdict: 'allow', nextState: 'paused', errorCode: '', buttonEnabled: true },
  'plugin_degraded|plugin_toggle': { verdict: 'allow', nextState: null, errorCode: '', note: '可顯式重試啟用', buttonEnabled: true },
  'plugin_degraded|resume': { verdict: 'allow', nextState: 'running', errorCode: '', note: '恢復時不自動重試失敗插件（§9.1）', buttonEnabled: true },
  'running|audit': { verdict: 'sequence', nextState: 'paused', errorCode: '', note: '先 pause 再 audit（§1.3）', buttonEnabled: true },
  'running|compile': { verdict: 'allow', nextState: 'compiling', errorCode: '', buttonEnabled: true },
  'running|deploy': { verdict: 'deny', nextState: null, errorCode: 'ERR_DEPLOY_BEFORE_COMPILE', buttonEnabled: false },
  'running|l0_refresh': { verdict: 'queue', nextState: null, errorCode: '', note: '預設佇列（策略可配）', buttonEnabled: true },
  'running|pause': { verdict: 'allow', nextState: 'paused', errorCode: '', note: '等 inflight 自然完成，禁止強制 abort', buttonEnabled: true },
  'running|plugin_toggle': { verdict: 'allow', nextState: null, errorCode: '', note: '不中斷 inflight；UI 鎖定避免重複提交', buttonEnabled: true },
  'running|resume': { verdict: 'deny', nextState: null, errorCode: 'ERR_RESUME_WHILE_RUNNING', buttonEnabled: false },
  'sandboxing|audit': { verdict: 'deny', nextState: null, errorCode: 'ERR_AUDIT_WHILE_COMPILING', note: '編譯結束後可審計包含編譯記錄的完整軌跡（§9.1）', buttonEnabled: false },
  'sandboxing|compile': { verdict: 'deny', nextState: null, errorCode: 'ERR_DUPLICATE_COMPILE', buttonEnabled: false },
  'sandboxing|deploy': { verdict: 'deny', nextState: null, errorCode: 'ERR_DEPLOY_BEFORE_COMPILE', note: '沙盒未通過不得部署', buttonEnabled: false },
  'sandboxing|l0_refresh': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'sandboxing|pause': { verdict: 'allow', nextState: 'paused', errorCode: '', buttonEnabled: true },
  'sandboxing|plugin_toggle': { verdict: 'queue', nextState: null, errorCode: '', buttonEnabled: true },
  'sandboxing|resume': { verdict: 'deny', nextState: null, errorCode: 'ERR_RESUME_BEFORE_AUDIT_END', note: '沙盒驗證中不可恢復', buttonEnabled: false },
};
/* GENERATED:END */

/**
 * 未列舉組合（如同態自轉 `pause@paused`）視為 no-op 允許、不轉態，
 * 與後端 `evaluate()` 的語義一致。
 *
 * 注意：**不得**再讓「矩陣缺格」落到 allow——矩陣已由後端全量生成，
 * 缺格代表生成腳本有漏，屬錯誤而非預設放行。故此處對已知 action 缺格
 * 採保守 DENY。
 */
export function evaluate(state: TaskRuntimeState | string, action: TaskAction | string): MatrixDecision {
  const key = state + '|' + action;
  const hit = MATRIX[key];
  if (hit) return hit;
  const knownAction = (TASK_ACTIONS as readonly string[]).includes(action);
  const knownState = (TASK_RUNTIME_STATES as readonly string[]).includes(state);
  if (knownAction && knownState) {
    return {
      verdict: 'deny',
      errorCode: 'ERR_MATRIX_CELL_MISSING',
      note: '後端矩陣缺格，保守拒絕（請重跑 export_task_state_matrix.py）',
      buttonEnabled: false,
    };
  }
  return { verdict: 'allow', note: 'no-op（未知狀態／動作組合）', buttonEnabled: true };
}

/** DENY → 禁用；其餘（含 QUEUE）可點擊提交。與 C-UI-002 一致。 */
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
