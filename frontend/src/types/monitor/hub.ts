/** AI Hub 監控（GET /monitor/hub）型別。 */

export interface HubMonitorModel {
  id: string;
  provider: string;
  intelligence: number;
  latency_ewma_ms: number | null;
  ttfb_ms: number | null;
  price_in_per_1m: number | null;
  price_out_per_1m: number | null;
  price_cached_in_per_1m?: number | null;
  price_cache_write_per_1m?: number | null;
  price_reasoning_per_1m?: number | null;
  price_image_per_1m?: number | null;
  price_audio_per_1m?: number | null;
  consecutive_fail: number;
  ts?: number;
  available_in_pool?: boolean;
  mapped_model?: string;
  circuit: {
    state: string;
    fail_ratio?: number;
    window_calls?: number;
    open_cycles?: number;
    disabled?: boolean;
  };
}

export interface HubCallLog {
  id?: string;
  user_id?: string;
  session_id?: string;
  provider?: string;
  model_name?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  cost_usd?: number;
  status?: string;
  latency_ms?: number;
  error_code?: string;
  create_time?: string;
  trace_id?: string;
}

export interface HubMonitorData {
  cache: {
    hits: number;
    misses: number;
    hit_rate: number;
    target_hit_rate: number;
  };
  upstream_calls: number;
  call_log_count: number;
  call_logs: HubCallLog[];
  models: HubMonitorModel[];
  circuits: Record<string, HubMonitorModel['circuit']>;
  budgets: Array<{
    name: string;
    spent_today_usd: number;
    daily_limit_usd: number;
    monthly_limit_usd: number;
    remaining_today_usd: number;
  }>;
  agent_tasks: Array<{
    task_id: string;
    status: string;
    input: string;
    tools: string[];
    cost_usd: number;
    chosen_provider: string;
    latency_ms: number;
    progress_pct: number;
    error_code: string;
    trace_id: string;
    created_at: string | null;
  }>;
  routing: {
    default_chain: string[];
    cn_chain: string[];
    race_pair: string[];
    forbidden_vendor: string;
    pool_lock?: {
      provider_kind: string;
      provider_label: string;
      lock_message: string;
      allowed_models: string[];
    };
  };
}
