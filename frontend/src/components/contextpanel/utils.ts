/**
 * Context 面板共用常數與小工具。
 */
import type {
  CompositionKey,
  ContextEventKind,
  ContextInsight,
  FilePurpose,
} from '../../api/contextInsight';

/** embed 無任務時的空洞察（不回落全域最新軌跡） */
export function emptyInsightForDialog(message: string): ContextInsight {
  return {
    task_id: null,
    empty: true,
    message,
    stats: {},
    composition: {},
    trend: [],
    events: [],
    steps: [],
    selected_step: null,
    browser: { step: null, categories: {} },
    file_activity: [],
    agent_network: [],
  };
}

export const KEYS: CompositionKey[] = ['system', 'tools', 'user', 'injected', 'assistant', 'tool_results'];
export const KIND_FILTERS: ContextEventKind[] = ['inject', 'compact', 'prune', 'switch', 'mode'];
export const FILE_FILTERS: Array<FilePurpose | 'all'> = ['all', 'read', 'written', 'searched', 'images'];

export const btnCls =
  'rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2.5 py-1 text-[11px] text-[var(--console-faint)] hover:text-[var(--console-ink)] disabled:opacity-40';
export const cardCls = 'rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-3';
