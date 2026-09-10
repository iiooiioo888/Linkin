/**
 * Context 洞察 API（對齊 dsh-context：組成／趨勢／事件／瀏覽器／檔案／席位網）。
 * @see https://github.com/bowenliang123/dsh-context
 */
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export type CompositionKey =
  | 'system'
  | 'tools'
  | 'user'
  | 'injected'
  | 'assistant'
  | 'tool_results';

export type ContextEventKind = 'inject' | 'compact' | 'prune' | 'switch' | 'mode';

export type FilePurpose = 'read' | 'written' | 'searched' | 'images';

export interface CompositionSlice {
  tokens: number;
  items: number;
  share: number;
}

export interface ContextBrowserItem {
  id: string;
  label: string;
  tokens: number;
  source: string;
  content: string;
}

export interface ContextFileActivity {
  path: string;
  purposes: FilePurpose[] | string[];
  ops_count: number;
  added: number;
  removed: number;
  hits: number;
  last_seq?: number;
  last_ts?: string;
  ops?: Array<{
    purpose: string;
    tool: string;
    seq?: number;
    ts?: string;
    added?: number;
    removed?: number;
  }>;
}

export interface ContextAgentNode {
  role: string;
  llm_calls: number;
  tokens_in: number;
  tokens_out: number;
  cost: number;
  duration_ms: number;
  parent?: string | null;
}

export interface ContextInsight {
  task_id: string | null;
  empty?: boolean;
  message?: string;
  stats: {
    llm_calls?: number;
    context_injections?: number;
    memory_operations?: number;
    tool_calls?: number;
    phase_changes?: number;
    compacts?: number;
    prunes?: number;
    inject_items?: number;
    est_window_tokens?: number;
    est_cost_usd?: number;
    avg_llm_ms?: number;
    context_pressure?: number;
    context_window?: number;
    file_touches?: number;
    agents?: number;
    event_counts?: Record<string, number>;
    timing?: {
      llm_ms?: number;
      tool_ms?: number;
      overhead_ms?: number;
      total_ms?: number;
      llm_share?: number;
      tool_share?: number;
      overhead_share?: number;
    };
  };
  composition: Partial<Record<CompositionKey, CompositionSlice>>;
  composition_keys?: CompositionKey[];
  trend: Array<{
    step: number;
    seq?: number;
    ts?: string;
    phase?: string;
    role?: string;
    model?: string;
    total_tokens: number;
    bars: Partial<Record<CompositionKey, number>>;
    delta_bars?: Partial<Record<CompositionKey, number>>;
    delta_tokens: number;
    marks: Array<{ kind: string; label: string }>;
  }>;
  events: Array<{
    kind: ContextEventKind | string;
    event: string;
    seq?: number;
    ts?: string;
    producer?: string;
    phase?: string;
    delta_tokens?: number;
    count?: number;
    summary?: string;
  }>;
  steps: Array<{
    step: number;
    seq?: number;
    ts?: string;
    model?: string;
    phase?: string;
    role?: string;
    prompt_tokens_est?: number;
    completion_tokens_est?: number;
  }>;
  selected_step: number | null;
  browser: {
    step: number | null;
    categories: Partial<Record<CompositionKey, ContextBrowserItem[]>>;
    vs_previous?: {
      prev_step: number;
      deltas: Partial<Record<CompositionKey, { tokens: number; items: number }>>;
    } | null;
    brief?: {
      user?: string;
      in?: string;
      response?: string;
      model?: string;
    } | null;
  };
  file_activity?: ContextFileActivity[];
  agent_network?: ContextAgentNode[];
  source?: string;
  heuristic?: string;
}

export async function fetchContextInsight(opts?: {
  taskId?: string | null;
  step?: number | null;
}): Promise<ContextInsight> {
  const params = new URLSearchParams();
  if (opts?.taskId) params.set('task_id', opts.taskId);
  if (opts?.step != null && Number.isFinite(opts.step)) params.set('step', String(opts.step));
  const q = params.toString();
  const url = opts?.taskId
    ? apiUrl(
        `/tasks/${encodeURIComponent(opts.taskId)}/context${
          opts.step != null && Number.isFinite(opts.step) ? `?step=${opts.step}` : ''
        }`,
      )
    : apiUrl(`/context${q ? `?${q}` : ''}`);
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`讀取 Context 洞察失敗（HTTP ${resp.status}）`);
  return resp.json();
}
