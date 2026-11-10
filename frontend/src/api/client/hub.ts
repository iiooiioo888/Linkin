/**
 * EvoLoop 後端 API 客戶端 — AI Hub 對外 API（/api/v1，不得剝除前綴）。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

// ==================== AI Hub（/api/v1，不得剝除前綴） ====================

export const HUB_DEV_API_KEY = 'ak_live_hub_dev_key_for_local_only';

function hubUrl(path: string): string {
  const base: string = import.meta.env.VITE_API_URL ?? '/api';
  return `${base}/v1${path}`;
}

function hubHeaders(apiKey: string, extra?: Record<string, string>): HeadersInit {
  return {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json; charset=utf-8',
    ...extra,
  };
}

async function readHubError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: string; title?: string; code?: string };
    return body.detail || body.title || body.code || `HTTP ${resp.status}`;
  } catch {
    return `請求失敗（HTTP ${resp.status}）`;
  }
}

export interface HubModelInfo {
  id: string;
  provider: string;
  intelligence: number;
  price_in_per_1m: number;
  price_out_per_1m: number;
  price_cached_in_per_1m?: number | null;
  price_cache_write_per_1m?: number | null;
  price_reasoning_per_1m?: number | null;
  price_image_per_1m?: number | null;
  price_audio_per_1m?: number | null;
  cn_allowed: boolean;
  available_in_pool?: boolean;
}

export interface HubCatalog {
  models: HubModelInfo[];
  strategies: string[];
  default_chain: string[];
  cn_set: string[];
  race_pair: string[];
  quality_flagship: string;
  pool_lock?: {
    provider_kind: string;
    provider_label: string;
    lock_message: string;
    allowed_models: string[];
  };
}

export interface HubChatResult {
  id: string;
  model: string;
  chosen_provider: string;
  cost_usd: number;
  latency_ms: number;
  routing_strategy: string;
  failover_hops: number;
  cache: string;
  notice?: string;
  race?: boolean;
  choices: Array<{ message: { role: string; content: string }; finish_reason: string }>;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export interface HubAgentCreateResult {
  task_id: string;
  status: string;
  poll_url: string;
  eta_ms: number;
}

export interface HubAgentTask {
  task_id: string;
  status: string;
  progress_pct: number;
  chosen_provider: string | null;
  cost_usd: number;
  latency_ms: number | null;
  trace_id?: string;
  result?: {
    content?: string;
    model?: string;
    failover_hops?: number;
    tool_traces?: Array<{
      tool: string;
      latency_ms: number;
      http_status: number;
      data?: Record<string, unknown>;
    }>;
  };
  error?: { code?: string; detail?: string };
}

export async function fetchHubCatalog(apiKey: string = HUB_DEV_API_KEY): Promise<HubCatalog> {
  const resp = await fetch(hubUrl('/catalog'), { headers: hubHeaders(apiKey) });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

export async function hubChatCompletion(opts: {
  apiKey?: string;
  prompt: string;
  strategy: string;
  region: string;
  model?: string;
  maxTokens?: number;
}): Promise<HubChatResult> {
  const extra: Record<string, string> = {
    'x-routing-strategy': opts.strategy,
    'X-Client-Region': opts.region,
  };
  const body: Record<string, unknown> = {
    messages: [{ role: 'user', content: opts.prompt }],
    temperature: 0.2,
    max_tokens: opts.maxTokens ?? 2048,
  };
  if (opts.model) body.model = opts.model;
  const resp = await fetch(hubUrl('/chat/completions'), {
    method: 'POST',
    headers: hubHeaders(opts.apiKey ?? HUB_DEV_API_KEY, extra),
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

export async function hubCreateAgentTask(opts: {
  apiKey?: string;
  input: string;
  tools?: string[];
  strategy?: string;
  region?: string;
}): Promise<HubAgentCreateResult> {
  const extra: Record<string, string> = {
    'x-routing-strategy': opts.strategy ?? 'quality_first',
    'X-Client-Region': opts.region ?? 'TW',
  };
  const resp = await fetch(hubUrl('/agent/tasks'), {
    method: 'POST',
    headers: hubHeaders(opts.apiKey ?? HUB_DEV_API_KEY, extra),
    body: JSON.stringify({
      input: opts.input,
      tools: opts.tools ?? ['StocksX_get_price'],
      timeout_seconds: 300,
    }),
  });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

export async function hubGetAgentTask(
  taskId: string,
  apiKey: string = HUB_DEV_API_KEY,
): Promise<HubAgentTask> {
  const resp = await fetch(hubUrl(`/agent/tasks/${encodeURIComponent(taskId)}`), {
    headers: hubHeaders(apiKey),
  });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}
