// ==================== 監控中心（GET /monitor/opc · /monitor/hub · /monitor/agents） ====================

import type { AuditRecord } from './dashboard';
import type { RahoDirectoryEntry, RahoGrillEdge } from './raho';
import type { TaskProgress } from './task';

export interface OpcTagCatalog {
  name: string;
  unit: string;
  desc: string;
  range: number[];
  writable: boolean;
}

export interface OpcLiveReading {
  tag_name: string;
  value: unknown;
  data_type?: string;
  quality?: string;
  source_timestamp?: string | null;
}

export interface OpcMonitorData {
  guard: {
    write_whitelist: string[];
    write_bounds: Record<string, { min: number; max: number }>;
    require_approval: boolean;
    sim_enabled: boolean;
    opc_server: string;
  };
  catalog: OpcTagCatalog[];
  audit: { recent: AuditRecord[]; summary: Record<string, number> };
    live: {
    reachable: boolean;
    health: { status?: string; opc_connected?: boolean; opc_server?: string } | null;
    browse_tags: Array<Record<string, unknown>>;
    readings: OpcLiveReading[];
    simulated?: boolean;
    error: string | null;
  };
  recent_tasks: TaskProgress[];
  service_url: string;
}

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

export interface AgentWorkItem {
  id: string;
  title: string;
  description: string;
  status: string;
  kind: 'assigned' | 'review' | 'coordinate' | 'synthesize' | string;
  assignee: string | null;
  task_id: string;
  task_query: string;
  task_status: string;
  phase: string;
  cost_usd: number;
  estimated_cost?: number;
  output_preview: string;
  updated_at: string | null;
  source: 'live' | 'run_log' | string;
  depends_on?: string[];
  tier?: string;
  feedback?: unknown[];
}

export interface AgentEvent {
  ts: string | null;
  event: string;
  item_id?: string | null;
  title: string;
  assignee: string | null;
  task_id: string | null;
  cost_usd: number;
  score?: number | null;
  degraded?: boolean;
}

export interface AgentCompanyTask {
  task_id: string;
  query: string;
  status: string;
  phase: string;
}

export interface AgentMetrics {
  review_pass: number;
  review_rework: number;
  review_force: number;
  errors: number;
  tool_calls: number;
  budget_alerts: number;
  items_total?: number;
  success_rate?: number;
  avg_cost_usd?: number;
  capacity_pct?: number;
  daily_spent_usd?: number;
  /** API（LLM）用量花費 */
  api_spent_usd?: number;
  /** 雲資源（Docker + 阿里雲）分攤 */
  cloud_spent_usd?: number;
  avg_latency_ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  last_model?: string;
  sla_breaches?: number;
  retries?: number;
  failovers?: number;
  cache_hits?: number;
  human_escalations?: number;
  p95_latency_ms?: number;
  weekly_spent_usd?: number;
  weekly_cloud_spent_usd?: number;
  grill_count?: number;
  grill_rate?: number;
  decision_clarity?: number;
  demoted?: boolean;
  raho_rank?: 'ok' | 'watch' | 'demoted' | string;
}

export interface AgentAlert {
  level: 'info' | 'warning' | 'critical' | string;
  message: string;
}

export interface RolePreset {
  id: string;
  name: string;
  level: number;
  category: string;
  reporting_to?: string | null;
  system_prompt: string;
  responsibilities: string[];
  default_tier: string;
  hint?: string;
}

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

export interface AgentCatalogMeta {
  categories: Array<{ id: string; label: string }>;
  tiers: Array<{ id: string; label: string }>;
  levels: Array<{ level: number; label: string }>;
  tool_names: string[];
  builtin_ids: string[];
  allowed_models?: string[];
  api_routes?: Array<{
    id: string;
    name: string;
    provider: string;
    provider_label: string;
    model: string;
    allowed_models: string[];
    enabled: boolean;
    configured?: boolean;
    is_default?: boolean;
  }>;
  models_by_provider?: ModelsByProvider[];
  model_token_hints?: Record<string, { max_context: number; max_output: number }>;
  model_rate_cards?: ModelRateCatalog;
  routing_strategies?: Array<{ id: string; label: string }>;
  role_presets?: RolePreset[];
  org_templates?: Array<{ id: string; name: string; description: string; role_count: number }>;
}

export interface AgentMonitorPrefs {
  poll_interval_ms: number;
  show_disabled: boolean;
  show_idle: boolean;
  show_custom_only: boolean;
  group_by?: 'level' | 'category' | string;
  compact_cards?: boolean;
  default_desk_tab?: 'tasks' | 'monitor' | 'settings' | 'org' | string;
  sort_by?: 'level' | 'name' | 'status' | 'cost' | 'queue' | string;
  capacity_warn_pct?: number;
  show_prompt_preview?: boolean;
  highlight_alerts?: boolean;
  auto_open_busy?: boolean;
  default_layout?: 'catalog' | 'desk' | 'floor' | string;
  sound_on_alert?: boolean;
  show_cost_in_cards?: boolean;
  pin_role_ids?: string[];
  filter_min_level?: number;
  filter_max_level?: number;
  timezone?: string;
  show_on_call_only?: boolean;
}

export interface RoleAgent {
  id: string;
  name: string;
  level: number;
  level_label: string;
  raho_layer?: number;
  raho_label?: string;
  raho_short?: string;
  raho_title?: string;
  raho_spine?: boolean;
  raho_lane?: string;
  raho_lane_label?: string;
  grill_targets?: string[];
  grill_target_labels?: string[];
  reports_to?: string | null;
  escalate_targets?: string[];
  escalate_target_labels?: string[];
  submit_targets?: string[];
  submit_target_labels?: string[];
  raho_independent?: boolean;
  category: string;
  reporting_to: string | null;
  can_delegate_to: string[];
  direct_reports: string[];
  responsibilities: string[];
  system_prompt?: string;
  max_parallel_work: number;
  default_tier: string;
  preferred_model?: string;
  preferred_provider?: string;
  daily_budget_usd?: number;
  weekly_budget_usd?: number;
  monthly_budget_usd?: number;
  cloud_daily_budget_usd?: number;
  cloud_weekly_budget_usd?: number;
  cloud_monthly_budget_usd?: number;
  tools_allowed?: string[];
  notes?: string;
  enabled?: boolean;
  is_custom?: boolean;
  is_builtin?: boolean;
  alert_on_error?: boolean;
  alert_on_budget?: boolean;
  alert_on_sla?: boolean;
  temperature?: number;
  max_output_tokens?: number;
  timeout_ms?: number;
  routing_strategy?: string;
  failover_models?: string[];
  sla_latency_ms?: number;
  max_retries?: number;
  language?: string;
  always_require_review?: boolean;
  priority?: number;
  description?: string;
  max_daily_items?: number;
  require_human_approval?: boolean;
  stream_enabled?: boolean;
  cache_enabled?: boolean;
  pii_redact?: boolean;
  mainland_only?: boolean;
  heartbeat_sec?: number;
  on_call?: boolean;
  tags?: string[];
  notify_channel?: string;
  quiet_hours?: string;
  context_window?: number;
  allow_tool_use?: boolean;
  auto_escalate?: boolean;
  templates: string[];
  alerts?: AgentAlert[];
  status: 'idle' | 'busy' | 'waiting' | 'error' | 'disabled' | string;
  inbox: Record<string, number>;
  queue: number;
  executing: number;
  done: number;
  blocked: number;
  cost_usd: number;
  /** API（LLM token）用量 */
  api_cost_usd?: number;
  /** 雲資源分攤合計（Docker + 阿里雲） */
  cloud_cost_usd?: number;
  docker_cost_usd?: number;
  aliyun_cost_usd?: number;
  last_activity_at: string | null;
  work_items: AgentWorkItem[];
  events: AgentEvent[];
  active_task_ids: string[];
  current_item: AgentWorkItem | null;
  company_tasks: AgentCompanyTask[];
  capacity_used: number;
  budget_remaining_usd?: number | null;
  budget_over?: boolean;
  ai_budget_remaining_usd?: number | null;
  ai_budget_over?: boolean;
  cloud_budget_remaining_usd?: number | null;
  cloud_budget_over?: boolean;
  metrics: AgentMetrics;
  demoted?: boolean;
  raho_rank?: 'ok' | 'watch' | 'demoted' | string;
}

export interface AccountBudgetSnapshot {
  hub_daily?: {
    label: string;
    unit: string;
    spent_today_usd: number;
    daily_limit_usd: number;
    remaining_today_usd: number | null;
  } | null;
  linkin_credits?: {
    label: string;
    unit: string;
    balance_credits: number;
    monthly_quota_credits: number;
    monthly_used_credits: number;
  } | null;
}

export interface AgentMonitorData {
  generated_at: string;
  account_budget?: AccountBudgetSnapshot;
  summary: {
    roles_total: number;
    roles_busy: number;
    roles_waiting: number;
    roles_idle: number;
    roles_custom?: number;
    roles_disabled?: number;
    roles_enabled?: number;
    alerts_open?: number;
    work_items_open: number;
    work_items_done: number;
    company_tasks: number;
    running_company_tasks: number;
    total_cost_usd?: number;
    total_api_cost_usd?: number;
    total_cloud_cost_usd?: number;
    total_docker_cost_usd?: number;
    total_aliyun_cost_usd?: number;
    roles_on_call?: number;
    roles_need_approval?: number;
    roles_mainland_only?: number;
  };
  levels: Array<{ level: number; label: string }>;
  raho_layers?: RahoDirectoryEntry[];
  grill_chain?: RahoGrillEdge[];
  catalog_meta?: AgentCatalogMeta;
  monitor_prefs?: AgentMonitorPrefs;
  agents: RoleAgent[];
}
