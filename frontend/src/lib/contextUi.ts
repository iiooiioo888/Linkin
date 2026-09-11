/**
 * Context 可視化常數與導航（靈感來自 dsh-context）。
 * https://github.com/bowenliang123/dsh-context
 *
 * 三表面：
 * - **主**：對話底部詳細區（永遠鎖死本會話 taskId；無任務選擇器；切換會話即 remount）
 * - **次**：控制台鏡像 #/monitor/context（可選任務）
 * - **Peek**：浮動模態（須顯式傳入本對話 taskId；無 ID 顯示空態，不抓全域軌跡）
 */
import type {
  CompositionKey,
  ContextEventKind,
  ContextInsight,
  FilePurpose,
} from '../api/contextInsight';

export const COMPOSITION_META: Record<
  CompositionKey,
  { label: string; color: string; short: string }
> = {
  system: { label: '系統提示', color: 'var(--console-blue)', short: 'Sys' },
  tools: { label: '工具綱要', color: '#BF5AF2', short: 'Tools' },
  user: { label: '用戶訊息', color: 'var(--console-green)', short: 'User' },
  injected: { label: '注入上下文', color: 'var(--console-amber)', short: 'Inj' },
  assistant: { label: '助手回覆', color: '#0A84FF', short: 'Asst' },
  tool_results: { label: '工具結果', color: 'var(--console-danger)', short: 'Res' },
};

export const EVENT_KIND_META: Record<
  ContextEventKind,
  { label: string; tone: string }
> = {
  inject: { label: 'Inject', tone: 'console-status-amber' },
  compact: { label: 'Compact', tone: 'console-status-blue' },
  prune: { label: 'Prune', tone: 'console-status-danger' },
  switch: { label: 'Switch', tone: 'text-[#BF5AF2]' },
  mode: { label: 'Mode', tone: 'text-[var(--console-sub)]' },
};

export const FILE_PURPOSE_META: Record<FilePurpose, { label: string; tone: string }> = {
  read: { label: 'Read', tone: 'console-status-blue' },
  written: { label: 'Written', tone: 'console-status-green' },
  searched: { label: 'Searched', tone: 'console-status-amber' },
  images: { label: 'Images', tone: 'text-[#BF5AF2]' },
};

export type TrendMode = 'total' | 'delta';
/** Step＝每次 llm_call；Turn＝同 phase 連續步驟合併（對齊 dsh-context 粒度） */
export type TrendGranularity = 'step' | 'turn';

const TREND_MODE_KEY = 'linkin.context.trendMode';
const TREND_GRAN_KEY = 'linkin.context.trendGranularity';

export function loadTrendMode(): TrendMode {
  try {
    const v = localStorage.getItem(TREND_MODE_KEY);
    return v === 'delta' ? 'delta' : 'total';
  } catch {
    return 'total';
  }
}

export function saveTrendMode(mode: TrendMode) {
  try {
    localStorage.setItem(TREND_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function loadTrendGranularity(): TrendGranularity {
  try {
    const v = localStorage.getItem(TREND_GRAN_KEY);
    return v === 'turn' ? 'turn' : 'step';
  } catch {
    return 'step';
  }
}

export function saveTrendGranularity(g: TrendGranularity) {
  try {
    localStorage.setItem(TREND_GRAN_KEY, g);
  } catch {
    /* ignore */
  }
}

export type TrendRow = ContextInsight['trend'][number] & {
  /** Turn 模式下對應的原始 step 清單；點選時取最後一步開 Browser */
  member_steps?: number[];
};

/** 將同 phase 連續步驟合併為 Turn 柱（累計窗口取末步；delta 加總） */
export function aggregateTrendByTurn(trend: ContextInsight['trend']): TrendRow[] {
  if (!trend.length) return [];
  const out: TrendRow[] = [];
  for (const row of trend) {
    const phase = row.phase || '';
    const last = out[out.length - 1];
    if (!last || (last.phase || '') !== phase) {
      out.push({
        ...row,
        step: out.length,
        member_steps: [row.step],
        marks: [...(row.marks || [])],
        delta_bars: { ...(row.delta_bars || row.bars || {}) },
      });
      continue;
    }
    last.total_tokens = row.total_tokens;
    last.bars = { ...row.bars };
    last.delta_tokens = (last.delta_tokens || 0) + (row.delta_tokens || 0);
    const db = { ...(last.delta_bars || {}) };
    const src = row.delta_bars || row.bars || {};
    for (const [k, v] of Object.entries(src)) {
      db[k as CompositionKey] = (db[k as CompositionKey] || 0) + (v || 0);
    }
    last.delta_bars = db;
    last.marks = [...(last.marks || []), ...(row.marks || [])];
    last.member_steps = [...(last.member_steps || []), row.step];
    last.model = row.model;
    last.role = row.role;
    last.ts = row.ts;
    last.seq = row.seq;
  }
  return out;
}

const PENDING_CONTEXT_KEY = 'linkin.openContext';

/** 自訂事件：開啟對話底部詳細區 Context 分頁（主表面） */
export const OPEN_CHAT_CONTEXT_EVENT = 'linkin:open-chat-context';
/** 自訂事件：浮動 Peek 模態（次級；對齊 dsh-context /context 居中預覽） */
export const OPEN_CONTEXT_MODAL_EVENT = 'linkin:open-context-modal';

export type OpenChatContextDetail = { taskId?: string | null };
export type OpenContextModalDetail = { taskId?: string | null };

function writePendingContext(taskId?: string | null) {
  try {
    sessionStorage.setItem(
      PENDING_CONTEXT_KEY,
      JSON.stringify({ taskId: taskId ?? null, ts: Date.now() }),
    );
  } catch {
    /* ignore */
  }
}

/** ChatView 掛載時消費；若有待開啟請求則回傳 taskId */
export function consumePendingChatContext(): string | null | undefined {
  try {
    const raw = sessionStorage.getItem(PENDING_CONTEXT_KEY);
    if (!raw) return undefined;
    sessionStorage.removeItem(PENDING_CONTEXT_KEY);
    const parsed = JSON.parse(raw) as { taskId?: string | null; ts?: number };
    if (Date.now() - (parsed.ts || 0) > 8000) return undefined;
    return parsed.taskId ?? null;
  } catch {
    return undefined;
  }
}

/**
 * 優先打開對話詳細位 Context 分頁。
 * 若不在對話視圖，先切回 `#/chat` 並寫入 pending，供 ChatView 掛載後展開。
 */
export function openChatContextDetail(taskId?: string | null) {
  const hash = window.location.hash.replace(/^#/, '').replace(/^\/?/, '');
  const root = hash.split('/').filter(Boolean)[0] || 'chat';
  if (root !== 'chat') {
    writePendingContext(taskId);
    window.location.hash = '#/chat';
  }
  window.dispatchEvent(
    new CustomEvent<OpenChatContextDetail>(OPEN_CHAT_CONTEXT_EVENT, {
      detail: { taskId: taskId ?? null },
    }),
  );
}

/** 控制台完整鏡像（次級）；主表面請用 openChatContextDetail */
export function jumpToContext(taskId?: string | null) {
  const base = '#/monitor/context';
  window.location.hash = taskId ? `${base}/${encodeURIComponent(taskId)}` : base;
}

/** 浮動 Peek 模態；須傳入本對話 taskId。傳 null／省略＝空態，禁止回落其他會話。 */
export function openContextModal(taskId?: string | null) {
  window.dispatchEvent(
    new CustomEvent<OpenContextModalDetail>(OPEN_CONTEXT_MODAL_EVENT, {
      detail: { taskId: taskId ?? null },
    }),
  );
}

export function parseContextTaskId(hash = window.location.hash): string | null {
  const raw = hash.replace(/^#/, '').replace(/^\/?/, '');
  const parts = raw.split('/').filter(Boolean);
  if (parts[0] === 'monitor' && parts[1] === 'context' && parts[2]) {
    return decodeURIComponent(parts[2]);
  }
  return null;
}

export function fmtTokens(n: number | undefined | null): string {
  const v = Number(n) || 0;
  if (v >= 1000) return `${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`;
  return String(Math.round(v));
}

export function fmtPressure(p: number | undefined | null): string {
  return `${Math.round((Number(p) || 0) * 100)}%`;
}

/** dsh-context 風格來源晶片色調 */
export function sourceChipTone(source: string | undefined | null): string {
  const s = String(source || '');
  if (s.startsWith('mcp:')) return 'ctx-chip is-mcp';
  if (s.startsWith('dsh-') || s.startsWith('dsh:')) return 'ctx-chip is-dsh';
  if (s.startsWith('plugin:')) return 'ctx-chip is-plugin';
  if (s.startsWith('tool:')) return 'ctx-chip is-tool';
  return 'ctx-chip';
}

export type BrowserSort = 'size' | 'name';
