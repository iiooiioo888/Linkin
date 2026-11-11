/** LLM 路由、費率與優化監控型別。 */

export interface ModelRateItem {
  id: string;
  label: string;
  usd_per_1m: number;
  unit?: string;
}

export interface ModelRateCard {
  id: string;
  input: number;
  output: number;
  cached_input?: number;
  cache_write?: number;
  reasoning?: number;
  image?: number;
  image_output?: number;
  audio?: number;
  audio_output?: number;
  transcription?: number;
  video?: number;
  embedding?: number;
  search?: number;
  tool?: number;
  batch_input?: number;
  batch_output?: number;
  long_context?: number;
  request?: number;
  storage?: number;
  computer?: number;
  realtime?: number;
  file_search?: number;
  code_exec?: number;
  items: ModelRateItem[];
  currency?: string;
  unit?: string;
}

export interface ModelRateCatalog {
  currency?: string;
  unit?: string;
  fields?: Array<{ id: string; label: string; unit?: string }>;
  models?: ModelRateCard[];
  by_id?: Record<string, ModelRateCard>;
}

export interface LlmCatalogModel {
  id: string;
  name: string;
  owned_by: string;
  route_id?: string;
  route_name?: string;
}

export interface ApiRoutePublic {
  id: string;
  name: string;
  provider: string;
  provider_label: string;
  api_key: string;
  configured: boolean;
  api_base: string;
  model: string;
  allowed_models: string[];
  catalog: LlmCatalogModel[];
  catalog_source: string;
  catalog_error: string;
  catalog_fetched_at: string;
  catalog_url: string;
  weight: number;
  enabled: boolean;
  fallback: boolean;
  is_default: boolean;
  models_locked?: boolean;
  provider_routing?: Record<string, unknown> | null;
}

export interface ModelsByProvider {
  route_id: string;
  name: string;
  provider: string;
  provider_label: string;
  family?: string;
  enabled: boolean;
  models: string[];
}

export interface OptimizationRoadmapItem {
  priority: string;
  id: string;
  label: string;
  benefit: string;
  enabled: boolean;
  status: string;
  metric?: string;
}

export interface OptimizationMonitorData {
  roadmap: OptimizationRoadmapItem[];
  stage_router: Record<string, { tier: string; model: string }>;
  reflection: {
    pass_threshold: number;
    max_iterations: number;
    min_score_improvement: number;
    dynamic_threshold?: Record<string, unknown>;
    sample_threshold_simple?: number;
    sample_threshold_complex?: number;
  };
  merge_review_synth: { enabled: boolean };
  llm_cache: {
    hits: number;
    misses: number;
    semantic_hits: number;
    evictions: number;
    hit_rate: number;
    semantic_enabled: boolean;
    max_size: number;
  };
  routing_feedback: {
    total: number;
    simple_count: number;
    company_count: number;
    simple_avg_score: number;
    company_avg_score: number;
    adaptive_length_threshold: number;
  };
  user_feedback?: {
    total: number;
    satisfaction_rate: number;
    stats?: Record<string, number>;
    thumbs_up?: number;
    thumbs_down?: number;
  };
  feedback_analysis?: {
    total: number;
    satisfaction_rate: number;
    signal_counts: Record<string, number>;
    score_buckets: { low: number; mid: number; high: number };
    avg_score: number | null;
    word_cloud: Array<{ word: string; count: number; weight: number }>;
    recent: Array<{
      session_id?: string;
      signal?: string;
      score?: number | null;
      comment?: string;
    }>;
  };
  model_calls?: {
    total_calls: number;
    total_cost: number;
    avg_duration_ms: number | null;
    files_scanned: number;
    by_model: Array<{
      model: string;
      count: number;
      share_pct: number;
      cost: number;
      avg_duration_ms: number | null;
    }>;
    by_phase: Array<{ phase: string; count: number; share_pct: number }>;
  };
  edge_cache?: {
    source?: string;
    tier: string;
    edge_ttl_sec: number;
    max_size?: number;
    hit_rate?: number;
    cache_age_sec: number | null;
    cache_fresh: boolean;
    entry_count: number;
    reading_count?: number;
  };
  /** @deprecated 請改用 edge_cache；保留向後相容 */
  opc_edge?: {
    tier: string;
    edge_ttl_sec: number;
    cache_age_sec: number | null;
    cache_fresh: boolean;
    reading_count: number;
    entry_count?: number;
    max_size?: number;
    hit_rate?: number;
  };
  system_stats?: {
    tasks_total: number;
    tasks_running: number;
    tasks_pending?: number;
    tasks_completed: number;
    tasks_failed: number;
    success_rate: number;
    avg_score: number | null;
    total_iterations: number;
  };
  trace: { trace_count: number; recent: Array<{ task_id?: string; event_count?: number }> };
  reflection_trace?: {
    tasks_analyzed: number;
    files_scanned: number;
    early_stop_count: number;
    avg_iterations: number | null;
    avg_score_delta: number | null;
    improvement_rate_pct: number;
    avg_evaluate_duration_ms: number | null;
    avg_reflection_duration_ms: number | null;
    avg_loop_duration_ms: number | null;
    recent_cycles: Array<{
      task_id: string;
      iterations: number;
      score_start: number | null;
      score_end: number | null;
      score_delta: number | null;
      evaluate_duration_ms: number;
      reflection_duration_ms: number;
      loop_duration_ms: number;
      early_stop: boolean;
      last_ts: string;
    }>;
  };
}

export interface LlmOpsData {
  provider_kind: string;
  provider_label: string;
  single_vendor: boolean;
  lock_message: string;
  model: string;
  api_base: string;
  configured: boolean;
  allowed_models: string[];
  catalog: LlmCatalogModel[];
  catalog_source: string;
  catalog_url: string;
  catalog_fetched_at: string;
  catalog_error: string;
  route_strategy?: string;
  default_route_id?: string;
  api_routes?: ApiRoutePublic[];
  models_by_provider?: ModelsByProvider[];
  model_rate_cards?: ModelRateCatalog;
  model_token_hints?: Record<string, { max_context: number; max_output: number }>;
  route_strategies?: Array<{ id: string; label: string }>;
  provider_presets?: Array<{
    id: string;
    name: string;
    api_base: string;
    model: string;
    label: string;
  }>;
  ops: {
    refresh_interval_sec: number;
    last_ok_at: string;
    last_error: string;
    last_latency_ms: number;
    last_reason: string;
    consecutive_fail: number;
    stale: boolean;
    enabled: boolean;
    next_check_at?: string;
  };
}
