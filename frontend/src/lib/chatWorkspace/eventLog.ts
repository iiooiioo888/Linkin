/**
 * 任務事件 → 思考步驟／終端列／問題清單。
 */
import type { RahoPendingDecision, TaskEvent, TaskProgress } from '../../types';
import { eventBody } from '../splitThink';
import { nodeCode, type WsNode } from './kanban';
import type { WsProblem, WsTermLine, WsThinkingStep } from './types';

const EVENT_LABELS: Record<string, string> = {
  company_start: '公司啟動',
  company_done: '公司流程完成',
  phase_change: '階段切換',
  decompose_done: '分解完成',
  work_item_start: '開始執行',
  work_item_done: '執行完成',
  work_item_error: '執行失敗',
  work_item_retry: '重試',
  work_item_escalate: '升級處理',
  execute_done: '執行完成',
  synthesize_done: '整合完成',
  final_review_done: '最終審查',
  review_approved: '審查通過',
  tool_call: '調用工具',
  tool_result: '工具結果',
  cancel_requested: '請求取消',
  review_pass: '審查通過',
  review_rework: '審查退回',
  review_force_done: '強制完成',
  budget_warning: '預算警告',
  budget_degrade: '預算降級',
  evaluation: '評估',
  user_decision_needed: '決策阻塞點',
  grill_raised: '質詢發起',
  grill_resolved: '質詢已解',
  raho_timeout: '決策逾時',
};

const WARN_EVENTS = new Set([
  'work_item_error',
  'budget_warning',
  'budget_degrade',
  'user_decision_needed',
  'work_item_escalate',
  'cancel_requested',
  'grill_raised',
  'raho_timeout',
]);

function estimateTokens(text: string, fallback?: unknown): number {
  const n = typeof fallback === 'number' ? fallback : Number(fallback);
  if (Number.isFinite(n) && n > 0) return Math.round(n);
  return Math.max(12, Math.round(text.length / 4));
}

export function wsThinking(
  task: TaskProgress | null | undefined,
  liveThinking: string,
  pending: RahoPendingDecision[],
): WsThinkingStep[] {
  const steps: WsThinkingStep[] = [];
  const events: TaskEvent[] = task?.events ?? [];
  events.forEach((ev, i) => {
    const last = i === events.length - 1;
    const running = task?.status === 'running' || task?.status === 'pending';
    const title = EVENT_LABELS[ev.event] || ev.event.replace(/_/g, ' ');
    const text = eventBody(ev.data).trim();
    let kind: WsThinkingStep['kind'] = 'success';
    if (WARN_EVENTS.has(ev.event) || ev.event.includes('error')) kind = 'warning';
    else if (last && running) kind = 'process';
    const blob = `${title}\n${text}`;
    steps.push({
      id: `ev-${ev.ts}-${i}`,
      ts: ev.ts,
      title,
      text: text || title,
      kind,
      tokens: estimateTokens(blob, ev.data.tokens ?? ev.data.token),
    });
  });
  const think = liveThinking.trim();
  if (think) {
    steps.push({
      id: 'live-think',
      ts: Date.now() / 1000,
      title: '生成 DAG 節點結構',
      text: think.slice(0, 800),
      kind: 'process',
      tokens: estimateTokens(think),
    });
  }
  pending.forEach((p) => {
    steps.push({
      id: `dec-${p.decision_id}`,
      ts: p.created_at ?? Date.now() / 1000,
      title: '決策阻塞點觸發',
      text: p.question,
      kind: 'warning',
      tokens: estimateTokens(p.question),
    });
  });
  return steps.slice(-40);
}

export function wsTerminal(task: TaskProgress | null | undefined): WsTermLine[] {
  const events = task?.events ?? [];
  return events.slice(-40).map((ev) => {
    const label = EVENT_LABELS[ev.event] || ev.event;
    const body = eventBody(ev.data).replace(/\s+/g, ' ').trim().slice(0, 180);
    let kind: WsTermLine['kind'] = 'info';
    if (WARN_EVENTS.has(ev.event) || /warn|warning|degrade/i.test(ev.event)) kind = 'warn';
    if (ev.event.includes('error') || ev.event.includes('fail')) kind = 'err';
    if (ev.event === 'tool_call') kind = 'cmd';
    return { kind, text: body ? `[${label}] ${body}` : `[${label}]` };
  });
}

export function wsProblems(
  task: TaskProgress | null | undefined,
  pending: RahoPendingDecision[],
  nodes: WsNode[],
): WsProblem[] {
  const out: WsProblem[] = [];
  pending.forEach((p) => {
    out.push({
      id: p.decision_id,
      title: 'DecisionBlocker: 等待 L5 裁決',
      detail: p.question,
      tone: 'warn',
      loc: p.item_id ? `node ${p.item_id}` : undefined,
    });
  });
  if (task?.error) {
    out.push({
      id: `${task.task_id}-err`,
      title: `任務${task.status === 'failed' ? '失敗' : '異常'}`,
      detail: task.error,
      tone: 'err',
    });
  }
  nodes
    .filter((n) => n.status === 'blocked')
    .forEach((n) => {
      out.push({
        id: `blk-${n.item.id}`,
        title: `節點阻塞：${n.item.title}`,
        detail: (n.item.output || n.item.description || '等待上游或裁決').slice(0, 200),
        tone: 'warn',
        loc: nodeCode(n.item.id),
      });
    });
  return out;
}
