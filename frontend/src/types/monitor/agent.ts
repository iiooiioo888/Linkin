/** Agent 監控（GET /monitor/agents）型別。 */

import type { RahoDirectoryEntry, RahoGrillEdge } from '../raho';
import type { ModelRateCatalog, ModelsByProvider } from './llmops';

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
