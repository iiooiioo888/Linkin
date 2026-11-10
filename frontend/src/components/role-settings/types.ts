/**
 * 角色設定表單型別與草稿轉換：表單草稿、agent→草稿、草稿→API payload。
 */
import type { Dispatch, SetStateAction } from 'react';
import type { AgentCatalogMeta, RoleAgent } from '../../types';

export interface RoleSettingsDraft {
  name: string;
  enabled: boolean;
  system_prompt: string;
  responsibilitiesText: string;
  default_tier: string;
  max_parallel_work: number;
  preferred_model: string;
  preferred_provider: string;
  daily_budget_usd: number;
  weekly_budget_usd: number;
  monthly_budget_usd: number;
  cloud_daily_budget_usd: number;
  cloud_weekly_budget_usd: number;
  cloud_monthly_budget_usd: number;
  toolsText: string;
  notes: string;
  reporting_to: string;
  can_delegate_to: string;
  alert_on_error: boolean;
  alert_on_budget: boolean;
  alert_on_sla: boolean;
  level: number;
  category: string;
  temperature: number;
  max_output_tokens: number;
  timeout_ms: number;
  routing_strategy: string;
  failoverText: string;
  sla_latency_ms: number;
  max_retries: number;
  language: string;
  always_require_review: boolean;
  priority: number;
  description: string;
  max_daily_items: number;
  require_human_approval: boolean;
  stream_enabled: boolean;
  cache_enabled: boolean;
  pii_redact: boolean;
  mainland_only: boolean;
  heartbeat_sec: number;
  on_call: boolean;
  tagsText: string;
  notify_channel: string;
  quiet_hours: string;
  context_window: number;
  allow_tool_use: boolean;
  auto_escalate: boolean;
}

export function draftFromAgent(agent: RoleAgent): RoleSettingsDraft {
  return {
    name: agent.name,
    enabled: agent.enabled !== false,
    system_prompt: agent.system_prompt ?? '',
    responsibilitiesText: (agent.responsibilities ?? []).join('\n'),
    default_tier: agent.default_tier || 'routine',
    max_parallel_work: agent.max_parallel_work || 2,
    preferred_model: agent.preferred_model ?? '',
    preferred_provider: agent.preferred_provider ?? '',
    daily_budget_usd: agent.daily_budget_usd ?? 0,
    weekly_budget_usd: agent.weekly_budget_usd ?? 0,
    monthly_budget_usd: agent.monthly_budget_usd ?? 0,
    cloud_daily_budget_usd: agent.cloud_daily_budget_usd ?? 0,
    cloud_weekly_budget_usd: agent.cloud_weekly_budget_usd ?? 0,
    cloud_monthly_budget_usd: agent.cloud_monthly_budget_usd ?? 0,
    toolsText: (agent.tools_allowed ?? []).join(', '),
    notes: agent.notes ?? '',
    reporting_to: agent.reporting_to ?? '',
    can_delegate_to: (agent.can_delegate_to ?? []).join(', '),
    alert_on_error: agent.alert_on_error !== false,
    alert_on_budget: agent.alert_on_budget !== false,
    alert_on_sla: agent.alert_on_sla !== false,
    level: agent.level,
    category: agent.category || 'management',
    temperature: agent.temperature ?? 0.7,
    max_output_tokens: agent.max_output_tokens ?? 4096,
    timeout_ms: agent.timeout_ms ?? 120000,
    routing_strategy: agent.routing_strategy || 'quality_first',
    failoverText: (agent.failover_models ?? []).join(', '),
    sla_latency_ms: agent.sla_latency_ms ?? 0,
    max_retries: agent.max_retries ?? 3,
    language: agent.language || 'zh-TW',
    always_require_review: agent.always_require_review === true,
    priority: agent.priority ?? 3,
    description: agent.description ?? '',
    max_daily_items: agent.max_daily_items ?? 0,
    require_human_approval: agent.require_human_approval === true,
    stream_enabled: agent.stream_enabled !== false,
    cache_enabled: agent.cache_enabled !== false,
    pii_redact: agent.pii_redact !== false,
    mainland_only: agent.mainland_only === true,
    heartbeat_sec: agent.heartbeat_sec ?? 0,
    on_call: agent.on_call === true,
    tagsText: (agent.tags ?? []).join(', '),
    notify_channel: agent.notify_channel ?? '',
    quiet_hours: agent.quiet_hours ?? '',
    context_window: agent.context_window ?? 0,
    allow_tool_use: agent.allow_tool_use !== false,
    auto_escalate: agent.auto_escalate !== false,
  };
}

export function draftToPayload(draft: RoleSettingsDraft): Record<string, unknown> {
  return {
    name: draft.name,
    enabled: draft.enabled,
    system_prompt: draft.system_prompt,
    responsibilities: draft.responsibilitiesText.split('\n').map((s) => s.trim()).filter(Boolean),
    default_tier: draft.default_tier,
    max_parallel_work: draft.max_parallel_work,
    preferred_model: draft.preferred_model,
    preferred_provider: draft.preferred_provider,
    daily_budget_usd: draft.daily_budget_usd,
    weekly_budget_usd: draft.weekly_budget_usd,
    monthly_budget_usd: draft.monthly_budget_usd,
    cloud_daily_budget_usd: draft.cloud_daily_budget_usd,
    cloud_weekly_budget_usd: draft.cloud_weekly_budget_usd,
    cloud_monthly_budget_usd: draft.cloud_monthly_budget_usd,
    tools_allowed: draft.toolsText.split(',').map((s) => s.trim()).filter(Boolean),
    notes: draft.notes,
    reporting_to: draft.reporting_to || null,
    can_delegate_to: draft.can_delegate_to.split(',').map((s) => s.trim()).filter(Boolean),
    alert_on_error: draft.alert_on_error,
    alert_on_budget: draft.alert_on_budget,
    alert_on_sla: draft.alert_on_sla,
    level: draft.level,
    category: draft.category,
    temperature: draft.temperature,
    max_output_tokens: draft.max_output_tokens,
    timeout_ms: draft.timeout_ms,
    routing_strategy: draft.routing_strategy,
    failover_models: draft.failoverText.split(',').map((s) => s.trim()).filter(Boolean),
    sla_latency_ms: draft.sla_latency_ms,
    max_retries: draft.max_retries,
    language: draft.language,
    always_require_review: draft.always_require_review,
    priority: draft.priority,
    description: draft.description,
    max_daily_items: draft.max_daily_items,
    require_human_approval: draft.require_human_approval,
    stream_enabled: draft.stream_enabled,
    cache_enabled: draft.cache_enabled,
    pii_redact: draft.pii_redact,
    mainland_only: draft.mainland_only,
    heartbeat_sec: draft.heartbeat_sec,
    on_call: draft.on_call,
    tags: draft.tagsText.split(',').map((s) => s.trim()).filter(Boolean),
    notify_channel: draft.notify_channel,
    quiet_hours: draft.quiet_hours,
    context_window: draft.context_window,
    allow_tool_use: draft.allow_tool_use,
    auto_escalate: draft.auto_escalate,
  };
}

/** 主面板提供給各 section 的草稿 setter。 */
export type DraftUpdater = Dispatch<SetStateAction<RoleSettingsDraft>>;

export type RoleSettingsSection = 'identity' | 'model' | 'prompt' | 'runtime' | 'alerts';

export const SETTINGS_SECTIONS: Array<{
  id: RoleSettingsSection;
  icon: string;
  label: string;
  hint: string;
}> = [
  { id: 'identity', icon: '◈', label: '身分／組織', hint: '層級、匯報與指派' },
  { id: 'model', icon: '◉', label: '模型／Token', hint: '供應商、模型與輸出上限' },
  { id: 'prompt', icon: '✎', label: '提示詞／職責', hint: '系統提示詞與職責清單' },
  { id: 'runtime', icon: '⚙', label: '執行／合規', hint: '通知、上限與護欄' },
  { id: 'alerts', icon: '◇', label: '預算／告警／監控', hint: 'AI 與雲服務分開控管' },
];

export interface RoleSettingsPanelProps {
  agent: RoleAgent;
  catalog: AgentCatalogMeta | undefined;
  agents: RoleAgent[];
  saving: boolean;
  error: string | null;
  initialSection?: RoleSettingsSection;
  onSave: (draft: RoleSettingsDraft) => Promise<void>;
  onReset?: () => Promise<void>;
  onDelete?: () => Promise<void>;
  onClone?: (agent: RoleAgent) => void;
  onCreate?: () => void;
}
