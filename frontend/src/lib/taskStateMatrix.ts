/**
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
