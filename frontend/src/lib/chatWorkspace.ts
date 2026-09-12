/**
 * 對話工作台資料：把任務看板／事件／產出轉成 1.html 風格節點。
 */
import type { ChatMessage, KanbanItem, RahoPendingDecision, TaskEvent, TaskProgress } from '../types';
import { eventBody } from './splitThink';

export const WS_KANBAN_COLUMNS = [
  { key: 'queue', label: '隊列', statuses: ['planning', 'ready', 'blocked', 'cancelled'] },
  { key: 'executing', label: '執行中', statuses: ['executing', 'rework'] },
  { key: 'review', label: '審查中', statuses: ['in_review', 'done'] },
] as const;

export type WsColumnKey = (typeof WS_KANBAN_COLUMNS)[number]['key'];

export interface WsNode {
  item: KanbanItem;
  status: string;
  column: WsColumnKey;
  tags: string[];
  progress: number;
  action: string;
}

export interface WsThinkingStep {
  id: string;
  ts: number;
  title: string;
  text: string;
  kind: 'success' | 'process' | 'warning';
  code?: string;
  tokens?: number;
}

export interface WsFile {
  id: string;
  name: string;
  path: string;
  status: 'added' | 'modified' | 'deleted';
  content: string;
  itemId?: string;
  size?: string;
  time?: string;
}

export interface WsTreeRow {
  kind: 'dir' | 'file';
  name: string;
  path: string;
  depth: number;
  file?: WsFile;
}

export interface WsProblem {
  id: string;
  title: string;
  detail: string;
  tone: 'warn' | 'err';
  loc?: string;
}

export interface WsTermLine {
  kind: 'info' | 'warn' | 'err' | 'cmd' | 'out';
  text: string;
}

export interface WsCodeTok {
  t: string;
  k: 'plain' | 'keyword' | 'function' | 'string' | 'comment' | 'variable' | 'number';
}

const AVATAR_COLORS = ['#c9a961', '#7a92b8', '#6fa87f', '#82828c', '#9184b5', '#7aa8b8'];

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

const STATUS_PROGRESS: Record<string, number> = {
  planning: 0,
  ready: 8,
  blocked: 12,
  executing: 55,
  rework: 40,
  in_review: 100,
  done: 100,
};

const KEYWORDS = new Set([
  'export',
  'import',
  'from',
  'interface',
  'type',
  'class',
  'function',
  'const',
  'let',
  'return',
  'if',
  'else',
  'async',
  'await',
  'def',
  'class',
  'string',
  'number',
  'boolean',
  'true',
  'false',
  'null',
  'undefined',
]);

export function wsColumnKey(status: string): WsColumnKey {
  for (const col of WS_KANBAN_COLUMNS) {
    if ((col.statuses as readonly string[]).includes(status)) return col.key;
  }
  return 'queue';
}

export function flattenWsNodes(task: TaskProgress | null | undefined): WsNode[] {
  if (!task?.kanban) return [];
  const rows: WsNode[] = [];
  for (const [status, items] of Object.entries(task.kanban)) {
    for (const item of items) {
      rows.push({
        item,
        status,
        column: wsColumnKey(status),
        tags: wsNodeTags(item, status),
        progress: wsNodeProgress(item, status),
        action: String(item.current_action || '').trim(),
      });
    }
  }
  return rows;
}

export function nodeCode(id: string): string {
  const raw = String(id || '').trim();
  if (!raw) return 'NODE';
  if (/^n(ode)?[-_]?\w+/i.test(raw)) return raw.replace(/^node[-_]?/i, 'NODE-').toUpperCase();
  return `N-${raw.slice(0, 4).toUpperCase()}`;
}

export function avatarColor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export function avatarInitial(label: string): string {
  const t = label.trim();
  if (!t) return 'A';
  return (Array.from(t)[0] || 'A').toUpperCase();
}

function slugFile(title: string): string {
  const s = title
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '')
    .replace(/\s+/g, '_')
    .slice(0, 48);
  return s || 'output';
}

export function wsNodeTags(item: KanbanItem, status?: string): string[] {
  if (item.tags?.length) return item.tags.slice(0, 4);
  const tags: string[] = [];
  const blob = `${item.title} ${item.description || ''}`;
  const rules: Array<[string, RegExp]> = [
    ['API', /api|sse|endpoint|協議/i],
    ['Schema', /schema|資料結構|npc|quest/i],
    ['Design', /設計|design|架構|選型/i],
    ['Database', /資料庫|postgres|sql/i],
    ['Code', /程式|code|實作|typescript|python/i],
  ];
  for (const [label, re] of rules) {
    if (re.test(blob)) tags.push(label);
  }
  if (!tags.length && status) tags.push(status.replace(/_/g, ' '));
  return tags.slice(0, 3);
}

export function wsNodeProgress(item: KanbanItem, status: string): number {
  if (typeof item.progress === 'number' && item.progress >= 0 && item.progress <= 100) {
    return item.progress;
  }
  return STATUS_PROGRESS[status] ?? 0;
}

export function wsFiles(task: TaskProgress | null | undefined, nodes: WsNode[]): WsFile[] {
  const files: WsFile[] = [];
  const seen = new Set<string>();
  for (const row of nodes) {
    const listed = row.item.files ?? [];
    if (listed.length) {
      listed.forEach((f, i) => {
        const path = f.path || f.name;
        if (!path || seen.has(path)) return;
        seen.add(path);
        files.push({
          id: `${row.item.id}-${i}`,
          name: f.name || path.split('/').pop() || path,
          path,
          status: f.status === 'added' ? 'added' : f.status === 'deleted' ? 'deleted' : 'modified',
          content: (row.item.output || '').trim(),
          itemId: row.item.id,
          size: f.size,
        });
      });
      continue;
    }
    const output = (row.item.output || '').trim();
    if (!output) continue;
    const name = `${slugFile(row.item.title)}.md`;
    const path = `output/${name}`;
    if (seen.has(path)) continue;
    seen.add(path);
    files.push({
      id: row.item.id,
      name,
      path,
      status: row.status === 'done' ? 'added' : 'modified',
      content: output,
      itemId: row.item.id,
      size: `${output.length}B`,
    });
  }
  const answer = (task?.answer || '').trim();
  if (answer && !files.some((f) => f.content === answer)) {
    files.push({
      id: `${task?.task_id || 'task'}-answer`,
      name: 'deliverable.md',
      path: 'output/deliverable.md',
      status: task?.status === 'completed' ? 'added' : 'modified',
      content: answer,
      size: `${answer.length}B`,
    });
  }
  return files;
}

export function wsTreeRows(files: WsFile[]): WsTreeRow[] {
  const rows: WsTreeRow[] = [];
  const seen = new Set<string>();
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));
  for (const f of sorted) {
    const parts = f.path.split('/').filter(Boolean);
    let acc = '';
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1;
      acc = acc ? `${acc}/${part}` : part;
      if (!isFile) {
        if (seen.has(acc)) return;
        seen.add(acc);
        rows.push({ kind: 'dir', name: `${part}/`, path: acc, depth: i });
        return;
      }
      rows.push({ kind: 'file', name: part, path: acc, depth: i, file: f });
    });
  }
  return rows;
}

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

export function hasUnresolvedDecision(message: Pick<ChatMessage, 'taskState'>): boolean {
  return (message.taskState?.raho?.pending_decisions ?? []).some(
    (p) => !p.resolved && (p.choices?.length ?? 0) > 0,
  );
}

/**
 * 與後端 `_COMPANY_KEYWORDS` / `_complex_query_length` 對齊。
 * 自動模式下只有這類查詢才建任務、才分裂左右監控。
 */
const COMPANY_QUERY_RE =
  /开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|多步|架構|架构|重构|遷移|迁移|deploy|develop|build|implement|design|create|refactor|migrate|project|system|application|故事|小說|小说|撰寫|撰写|長文|长文|\d+\s*字/i;

const COMPANY_QUERY_LENGTH = 200;

export function looksLikeCompanyQuery(query: string): boolean {
  const q = (query || '').trim();
  if (!q) return false;
  if (q.length >= COMPANY_QUERY_LENGTH) return true;
  return COMPANY_QUERY_RE.test(q);
}

const TERMINAL_TASK_STATUSES = new Set<TaskProgress['status']>([
  'completed',
  'failed',
  'cancelled',
  'interrupted',
]);

function isRunningTaskStatus(status: TaskProgress['status'] | undefined): boolean {
  return status === 'running' || status === 'pending';
}

/** Grill 質詢尚未鎖定、未終止 → 仍算互動中 */
export function isGrillInteractive(message: Pick<ChatMessage, 'grill'>): boolean {
  const g = message.grill;
  return Boolean(g && !g.locked && !g.terminated);
}

/** L3 戰術地圖等待 L5 裁決 */
export function isBattleWaiting(message: Pick<ChatMessage, 'battle'>): boolean {
  const b = message.battle;
  return b?.status === 'ESCALATE_TO_USER' && Boolean(b.waiting_for_user_decision);
}

/**
 * 僅在任務仍 live／互動中時切右側監控欄。
 * 已完成／失敗／取消的歷史任務不切欄；寒暄 SSE、無任務的簡單對話亦不切欄。
 */
export function isLiveMonitorTask(
  message: Pick<ChatMessage, 'taskState' | 'taskId' | 'grill' | 'battle' | 'streaming'>,
): boolean {
  if (isGrillInteractive(message) || isBattleWaiting(message)) return true;
  if (hasUnresolvedDecision(message)) return true;

  const task = message.taskState;
  if (task) {
    if (isRunningTaskStatus(task.status)) return true;
    if (task.status === 'failed' || task.status === 'interrupted') return true;
    if (TERMINAL_TASK_STATUSES.has(task.status)) return false;
  }

  // 僅 taskId、尚無快照：任務剛建立、串流中才暫開監控
  if (message.taskId && !task) return Boolean(message.streaming);

  return false;
}

export function activeTaskMessage<T extends Pick<ChatMessage, 'taskState' | 'taskId'>>(
  messages: T[],
): T | null {
  return [...messages].reverse().find(isLiveMonitorTask) ?? null;
}

/** 進行中任務（不含失敗／已完成）— 用於精簡管線條。 */
export function runningTaskMessage<
  T extends Pick<ChatMessage, 'taskState' | 'taskId' | 'streaming'>,
>(messages: T[]): T | null {
  return (
    [...messages].reverse().find((m) => {
      const st = m.taskState?.status;
      if (st === 'running' || st === 'pending') return true;
      if (m.taskId && !m.taskState && m.streaming) return true;
      return false;
    }) ?? null
  );
}

/**
 * 解析 Context 面板應綁定的任務 ID（對話詳細區用）。
 *
 * **契約（對話頁 C-UI-004）**：
 * - 僅在本會話 `messages` 內解析；永遠綁定「進行中 → 否則最近一則」
 * - `prefer` 僅當屬於本會話才生效；外來／其他對話 ID **一律忽略**
 * - 不回落全域最新軌跡；UI 不得提供跨對話任務選擇器
 */
export function resolveContextTaskId(
  messages: Array<Pick<ChatMessage, 'taskState' | 'taskId'>>,
  prefer?: string | null,
): string | null {
  const sessionIds = new Set<string>();
  for (const m of messages) {
    const id = (m.taskId || m.taskState?.task_id || '').trim();
    if (id) sessionIds.add(id);
  }
  const explicit = (prefer || '').trim();
  // 僅當 prefer 確屬本會話才採用；外來 ID 一律忽略
  if (explicit && sessionIds.has(explicit)) return explicit;
  const live = activeTaskMessage(messages);
  const fromLive = (live?.taskId || live?.taskState?.task_id || '').trim();
  if (fromLive) return fromLive;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    const id = (m.taskId || m.taskState?.task_id || '').trim();
    if (id) return id;
  }
  return null;
}

export function numBudget(task: TaskProgress | null | undefined, key: string): number {
  const v = task?.budget?.[key];
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export function wsTokens(task: TaskProgress | null | undefined): number {
  const total = numBudget(task, 'tokens_total');
  if (total > 0) return total;
  const sum = numBudget(task, 'tokens_in') + numBudget(task, 'tokens_out');
  if (sum > 0) return sum;
  const fromNodes = flattenWsNodes(task).reduce((acc, n) => acc + (n.item.tokens || 0), 0);
  if (fromNodes > 0) return fromNodes;
  return (task?.events ?? []).length * 180;
}

export function langOf(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  if (ext === 'ts' || ext === 'tsx') return 'TypeScript';
  if (ext === 'js' || ext === 'jsx') return 'JavaScript';
  if (ext === 'py') return 'Python';
  if (ext === 'json') return 'JSON';
  if (ext === 'md') return 'Markdown';
  if (ext === 'css') return 'CSS';
  if (ext === 'html') return 'HTML';
  return ext.toUpperCase() || 'Text';
}

export function tokenizeCode(line: string): WsCodeTok[] {
  if (!line) return [{ t: ' ', k: 'plain' }];
  const out: WsCodeTok[] = [];
  const push = (t: string, k: WsCodeTok['k']) => {
    if (t) out.push({ t, k });
  };
  let rest = line;
  while (rest.length) {
    const comment = rest.match(/^(\/\/.*|#(?!\{).*)$/);
    if (comment) {
      push(comment[1], 'comment');
      break;
    }
    const str = rest.match(/^(['"`])(?:\\.|(?!\1).)*\1/);
    if (str) {
      push(str[0], 'string');
      rest = rest.slice(str[0].length);
      continue;
    }
    const num = rest.match(/^\d+(?:\.\d+)?/);
    if (num) {
      push(num[0], 'number');
      rest = rest.slice(num[0].length);
      continue;
    }
    const word = rest.match(/^[A-Za-z_][\w]*/);
    if (word) {
      const w = word[0];
      const next = rest.slice(w.length);
      if (KEYWORDS.has(w)) push(w, 'keyword');
      else if (next.startsWith('(')) push(w, 'function');
      else if (/^[A-Z]/.test(w)) push(w, 'variable');
      else push(w, 'plain');
      rest = next;
      continue;
    }
    push(rest[0], 'plain');
    rest = rest.slice(1);
  }
  return out.length ? out : [{ t: line, k: 'plain' }];
}
