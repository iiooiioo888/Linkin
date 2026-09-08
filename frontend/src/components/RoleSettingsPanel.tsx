/**
 * 角色設定表單：內建覆蓋 + 自定義角色建立／刪除／複製。
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import type { AgentCatalogMeta, RoleAgent, RolePreset } from '../types';
import { CATEGORY_LABEL, ROUTING_LABEL, TIER_LABEL, fmtUsd, routeDisplayName } from '../lib/agentUi';
import { agentRahoLabel } from '../lib/rahoUi';
import { navPathForTab } from '../lib/monitorTabs';
import PromptEditor from './PromptEditor';

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

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-[#62666d]">{label}</span>
      {hint && <span className="ml-2 text-[10px] text-[#8a8f98]">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}

const inputCls =
  'w-full rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px] text-[#f7f8f8] outline-none focus:border-[#007AFF]/60';

function tokenHint(
  model: string,
  hints?: Record<string, { max_context: number; max_output: number }>,
) {
  if (!hints || !model) return undefined;
  const bare = model.split('/').pop() || model;
  return hints[model] || hints[bare];
}

function routeOptionLabel(route: {
  name?: string;
  provider_label?: string;
  provider?: string;
  is_default?: boolean;
  enabled?: boolean;
}): string {
  const base = routeDisplayName(route) || '未命名 API';
  const bits = [base];
  if (route.is_default) bits.push('預設');
  if (route.enabled === false) bits.push('停用');
  return bits.join(' · ');
}

function TokenSlider({
  label,
  hint,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (n: number) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="flex items-center gap-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={Math.min(max, Math.max(min, value))}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1 accent-[#007AFF]"
        />
        <input
          type="number"
          min={min}
          max={max}
          className={`${inputCls} w-24`}
          value={value}
          onChange={(e) => onChange(Number(e.target.value) || min)}
        />
      </div>
    </Field>
  );
}

type RoleSettingsSection = 'identity' | 'model' | 'prompt' | 'runtime' | 'alerts';

const SETTINGS_SECTIONS: Array<{
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

interface RoleSettingsPanelProps {
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

export default function RoleSettingsPanel({
  agent,
  catalog,
  agents,
  saving,
  error,
  initialSection = 'identity',
  onSave,
  onReset,
  onDelete,
  onClone,
  onCreate,
}: RoleSettingsPanelProps) {
  const [draft, setDraft] = useState<RoleSettingsDraft>(() => draftFromAgent(agent));
  const [section, setSection] = useState<RoleSettingsSection>(initialSection);

  useEffect(() => {
    setDraft(draftFromAgent(agent));
  }, [agent]);

  useEffect(() => {
    setSection(initialSection);
  }, [agent.id, initialSection]);

  const goSection = (id: RoleSettingsSection) => {
    setSection(id);
    document.getElementById(`rs-${id}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  };

  const categories = catalog?.categories ?? Object.entries(CATEGORY_LABEL).map(([id, label]) => ({ id, label }));
  const tiers = catalog?.tiers ?? Object.entries(TIER_LABEL).map(([id, label]) => ({ id, label }));
  const levels = catalog?.levels ?? [];
  const tools = catalog?.tool_names ?? [];
  const routing = catalog?.routing_strategies ?? Object.entries(ROUTING_LABEL).map(([id, label]) => ({ id, label }));
  const selectedHint = tokenHint(draft.preferred_model, catalog?.model_token_hints);
  const outputMax = selectedHint?.max_output ?? 32768;
  const contextMax = selectedHint?.max_context ?? 2_000_000;
  const activeRoute =
    (catalog?.api_routes ?? []).find((r) => r.id === draft.preferred_provider) ||
    catalog?.api_routes?.find((r) => r.is_default);
  const defaultRoute = catalog?.api_routes?.find((r) => r.is_default);

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(draftFromAgent(agent)), [agent, draft]);
  const modelStatus = [
    routeDisplayName(activeRoute) || '全域預設',
    draft.preferred_model || 'API 預設模型',
    `輸出 ${draft.max_output_tokens.toLocaleString()}`,
    draft.context_window > 0 ? `上下文 ${draft.context_window.toLocaleString()}` : '上下文不截斷',
  ].join(' · ');

  return (
    <div className="rs-wrap">
      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12px] text-red-200">{error}</p>
      )}
      <div className="rs-toolbar">
        <div className="rs-head">
          <div className="rs-head-l">
            <h2 className="rs-title">角色設定</h2>
            <p className="rs-sub">
              {agent.is_custom
                ? '自定義角色，可刪除'
                : '內建角色 · 可覆蓋設定，還原後回到內建預設'}
            </p>
          </div>
          <div className="rs-actions">
            {onCreate && (
              <button type="button" onClick={onCreate} className="rs-act">
                新增角色
              </button>
            )}
            {onClone && (
              <button type="button" onClick={() => onClone(agent)} className="rs-act">
                複製為自定義
              </button>
            )}
            {onReset && !agent.is_custom && (
              <button type="button" onClick={() => void onReset()} className="rs-act">
                還原預設
              </button>
            )}
            {onDelete && agent.is_custom && (
              <button type="button" onClick={() => void onDelete()} className="rs-act rs-act--danger">
                刪除角色
              </button>
            )}
            <button
              type="button"
              disabled={saving || !dirty}
              onClick={() => void onSave(draft)}
              className="rs-act rs-act--primary"
            >
              {saving ? '儲存中…' : '儲存設定'}
            </button>
          </div>
        </div>
      </div>

      <div className="rs-body">
      <nav className="sp-nav rs-nav" aria-label="角色設定分區">
        <div className="sp-group">設定</div>
        <div className="sp-list">
          {SETTINGS_SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`sp-item ${section === item.id ? 'on' : ''}`}
              onClick={() => goSection(item.id)}
            >
              <span className="sp-item-ic">{item.icon}</span>
              <span className="sp-item-txt">
                <span className="sp-item-l">{item.label}</span>
                <span className="sp-item-h">{item.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </nav>
      <div className="min-w-0 space-y-3.5">
      <section id="rs-identity" className="rs-sec">
        <div className="rs-sec-h">
          <h3 className="rs-sec-t">身分／組織</h3>
          <span className="rs-sec-hint">質詢層走指揮／審查／核心三條線；組織職級只管公司匯報鏈</span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          <Field label="顯示名稱">
            <input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </Field>
          <Field label="啟用">
            <button
              type="button"
              onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
              className={`rounded-md border px-3 py-1.5 text-[12px] ${
                draft.enabled
                  ? 'border-[#4cc38a]/40 bg-[#4cc38a]/10 text-[#4cc38a]'
                  : 'border-red-500/30 bg-red-500/10 text-red-300'
              }`}
            >
              {draft.enabled ? '已啟用 · 可被指派' : '已停用 · 分解時排除'}
            </button>
          </Field>
          <Field label="質詢層">
            <input className={inputCls} value={agentRahoLabel(agent)} readOnly />
          </Field>
          <Field label="組織職級">
            <select
              className={inputCls}
              value={draft.level}
              onChange={(e) => setDraft({ ...draft, level: Number(e.target.value) })}
            >
              {levels.map((lv) => (
                <option key={lv.level} value={lv.level}>
                  {lv.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="分類">
            <select
              className={inputCls}
              value={draft.category}
              onChange={(e) => setDraft({ ...draft, category: e.target.value })}
            >
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="匯報對象">
            <select
              className={inputCls}
              value={draft.reporting_to}
              onChange={(e) => setDraft({ ...draft, reporting_to: e.target.value })}
            >
              <option value="">無上級</option>
              {agents
                .filter((a) => a.id !== agent.id)
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="可委派" hint="逗號分隔 id">
            <input
              className={inputCls}
              value={draft.can_delegate_to}
              onChange={(e) => setDraft({ ...draft, can_delegate_to: e.target.value })}
            />
          </Field>
          <Field label="並行上限">
            <input
              type="number"
              min={1}
              max={16}
              className={inputCls}
              value={draft.max_parallel_work}
              onChange={(e) => setDraft({ ...draft, max_parallel_work: Number(e.target.value) || 1 })}
            />
          </Field>
          <Field label="優先級" hint="1=最高 5=最低">
            <input
              type="number"
              min={1}
              max={5}
              className={inputCls}
              value={draft.priority}
              onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) || 3 })}
            />
          </Field>
          <Field label="輸出語言">
            <select
              className={inputCls}
              value={draft.language}
              onChange={(e) => setDraft({ ...draft, language: e.target.value })}
            >
              <option value="zh-TW">繁體中文</option>
              <option value="zh-CN">簡體中文</option>
              <option value="en">English</option>
            </select>
          </Field>
          <Field label="允許工具" hint={tools.length ? tools.join(' · ') : '逗號分隔'}>
            <input
              className={inputCls}
              value={draft.toolsText}
              onChange={(e) => setDraft({ ...draft, toolsText: e.target.value })}
            />
          </Field>
          <Field label="一句話職責" hint="目錄卡片摘要">
            <input
              className={inputCls}
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </Field>
        </div>
      </section>

      <section id="rs-model" className="rs-sec">
        <div className="rs-sec-h">
          <h3 className="rs-sec-t">模型／Token</h3>
          <span className="rs-sec-hint">供應商、模型與輸出上限</span>
        </div>
        <p className="rs-status" title={modelStatus}>
          {modelStatus}
        </p>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {(catalog?.api_routes?.length ?? 0) === 0 && catalog != null && (
            <p className="md:col-span-2 lg:col-span-3 rounded-xl border border-[#FF9F0A]/25 bg-[#FF9F0A]/8 px-3 py-2 text-[12px] text-[#FF9F0A]">
              尚未配置 API。請先到{' '}
              <a href="#/monitor/llm" className="font-medium underline">
                {navPathForTab('llm')}
              </a>{' '}
              加入千問／DeepSeek／Kimi／OpenRouter。
            </p>
          )}
          <Field label="模型層級">
            <select
              className={inputCls}
              value={draft.default_tier}
              onChange={(e) => setDraft({ ...draft, default_tier: e.target.value })}
            >
              {tiers.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="API 供應商" hint="空白=全域預設路由">
            <select
              className={inputCls}
              value={draft.preferred_provider}
              onChange={(e) => {
                const next = e.target.value;
                const group = (catalog?.models_by_provider ?? []).find((g) => g.route_id === next);
                const nextModel =
                  next && group && !group.models.includes(draft.preferred_model)
                    ? group.models[0] || ''
                    : draft.preferred_model;
                setDraft({ ...draft, preferred_provider: next, preferred_model: nextModel });
              }}
            >
              <option value="">全域預設（{routeDisplayName(defaultRoute) || '目前 API'}）</option>
              {(catalog?.api_routes ?? []).map((route) => (
                <option key={route.id} value={route.id} disabled={route.enabled === false}>
                  {routeOptionLabel(route)}
                </option>
              ))}
            </select>
          </Field>
          <Field label="指定模型" hint="依上方供應商列出可用模型；空白=該 API 預設">
            <select
              className={inputCls}
              value={draft.preferred_model}
              onChange={(e) => setDraft({ ...draft, preferred_model: e.target.value })}
            >
              <option value="">該 API 預設模型</option>
              {(catalog?.models_by_provider ?? []).length > 0
                ? (catalog?.models_by_provider ?? [])
                    .filter((g) => !draft.preferred_provider || g.route_id === draft.preferred_provider)
                    .map((g) => (
                      <optgroup key={g.route_id} label={routeDisplayName(g) || g.name}>
                        {g.models.map((id) => (
                          <option key={`${g.route_id}-${id}`} value={id}>
                            {id}
                          </option>
                        ))}
                      </optgroup>
                    ))
                : (catalog?.allowed_models ?? []).map((id) => (
                    <option key={id} value={id}>
                      {id}
                    </option>
                  ))}
            </select>
          </Field>
          <Field label="路由策略">
            <select
              className={inputCls}
              value={draft.routing_strategy}
              onChange={(e) => setDraft({ ...draft, routing_strategy: e.target.value })}
            >
              {routing.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="故障轉移模型" hint="逗號分隔，主模型失敗後依序切換">
            <input
              className={inputCls}
              placeholder="gemini-3.1-pro, deepseek-v4-flash"
              value={draft.failoverText}
              onChange={(e) => setDraft({ ...draft, failoverText: e.target.value })}
            />
          </Field>
          <Field label="溫度" hint="0=確定, 2=發散">
            <input
              type="number"
              min={0}
              max={2}
              step={0.1}
              className={inputCls}
              value={draft.temperature}
              onChange={(e) => setDraft({ ...draft, temperature: Number(e.target.value) })}
            />
          </Field>
          <TokenSlider
            label="最大輸出 Token"
            hint={
              selectedHint
                ? `單次回覆上限 · 此模型建議 ≤ ${outputMax.toLocaleString()}`
                : '單次回覆上限，寫入 API max_tokens'
            }
            value={draft.max_output_tokens}
            min={256}
            max={outputMax}
            step={256}
            onChange={(n) => setDraft({ ...draft, max_output_tokens: n || 4096 })}
          />
          <TokenSlider
            label="上下文 Token"
            hint={
              selectedHint
                ? `0=不截斷 · 此模型上下文 ${contextMax.toLocaleString()}`
                : '0=不截斷；超過則截斷提示'
            }
            value={draft.context_window}
            min={0}
            max={contextMax}
            step={1024}
            onChange={(n) => setDraft({ ...draft, context_window: n || 0 })}
          />
          <Field label="逾時毫秒">
            <input
              type="number"
              min={5000}
              max={600000}
              className={inputCls}
              value={draft.timeout_ms}
              onChange={(e) => setDraft({ ...draft, timeout_ms: Number(e.target.value) || 120000 })}
            />
          </Field>
          <Field label="最大重試">
            <input
              type="number"
              min={0}
              max={8}
              className={inputCls}
              value={draft.max_retries}
              onChange={(e) => setDraft({ ...draft, max_retries: Number(e.target.value) || 0 })}
            />
          </Field>
        </div>
      </section>

      <section id="rs-prompt" className="rs-sec">
        <div className="rs-sec-h">
          <h3 className="rs-sec-t">提示詞／職責</h3>
          <span className="rs-sec-hint">系統提示詞與職責清單</span>
        </div>
        <div className="space-y-3">
          <Field label="系統提示詞" hint="Monaco · 語法高亮">
            <PromptEditor
              value={draft.system_prompt}
              onChange={(v) => setDraft({ ...draft, system_prompt: v })}
              height={280}
            />
          </Field>
          <Field label="職責" hint="一行一項">
            <textarea
              rows={6}
              className={inputCls}
              value={draft.responsibilitiesText}
              onChange={(e) => setDraft({ ...draft, responsibilitiesText: e.target.value })}
            />
          </Field>
          <Field label="備註">
            <textarea
              rows={2}
              className={inputCls}
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </Field>
        </div>
      </section>

      <section id="rs-runtime" className="rs-sec">
        <div className="rs-sec-h">
          <h3 className="rs-sec-t">執行／合規</h3>
          <span className="rs-sec-hint">通知、上限與護欄</span>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          <Field label="標籤" hint="逗號分隔">
            <input className={inputCls} value={draft.tagsText} onChange={(e) => setDraft({ ...draft, tagsText: e.target.value })} />
          </Field>
          <Field label="通知頻道">
            <input className={inputCls} placeholder="slack:#ops / email" value={draft.notify_channel} onChange={(e) => setDraft({ ...draft, notify_channel: e.target.value })} />
          </Field>
          <Field label="安靜時段" hint="例 22:00-08:00">
            <input className={inputCls} value={draft.quiet_hours} onChange={(e) => setDraft({ ...draft, quiet_hours: e.target.value })} />
          </Field>
          <Field label="心跳秒數" hint="0=關閉">
            <input type="number" min={0} className={inputCls} value={draft.heartbeat_sec} onChange={(e) => setDraft({ ...draft, heartbeat_sec: Number(e.target.value) || 0 })} />
          </Field>
          <Field label="每日工作項上限" hint="0=不限">
            <input type="number" min={0} className={inputCls} value={draft.max_daily_items} onChange={(e) => setDraft({ ...draft, max_daily_items: Number(e.target.value) || 0 })} />
          </Field>
          <div className="flex flex-wrap gap-3 md:col-span-2">
            {[
              ['on_call', '值班中', draft.on_call],
              ['require_human_approval', '人工核准後才執行', draft.require_human_approval],
              ['stream_enabled', '允許串流', draft.stream_enabled],
              ['cache_enabled', '語義快取', draft.cache_enabled],
              ['pii_redact', '個資遮蔽', draft.pii_redact],
              ['mainland_only', '僅國內模型', draft.mainland_only],
              ['allow_tool_use', '允許工具', draft.allow_tool_use],
              ['auto_escalate', '失敗自動升級', draft.auto_escalate],
            ].map(([key, label, checked]) => (
              <label key={String(key)} className="flex items-center gap-2 text-[12px] text-[#d0d6e0]">
                <input
                  type="checkbox"
                  checked={Boolean(checked)}
                  onChange={(e) => setDraft({ ...draft, [key as string]: e.target.checked })}
                />
                {label as string}
              </label>
            ))}
          </div>
        </div>
      </section>

      <section id="rs-alerts" className="rs-sec">
        <div className="rs-sec-h">
          <h3 className="rs-sec-t">預算／告警／監控</h3>
          <span className="rs-sec-hint">AI 與雲服務分開控管 · 0=不限</span>
        </div>
        <div className="space-y-3">
          <div className="rs-budget-grid">
            <div className="rs-budget">
              <div className="rs-budget-h">
                <h4>AI 使用預算</h4>
                <span>今日已用 {fmtUsd(agent.api_cost_usd ?? agent.metrics?.api_spent_usd ?? 0)} · 只計 LLM</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Field label="每日 USD">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={inputCls}
                    value={draft.daily_budget_usd}
                    onChange={(e) => setDraft({ ...draft, daily_budget_usd: Number(e.target.value) || 0 })}
                  />
                </Field>
                <Field label="每週 USD">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={inputCls}
                    value={draft.weekly_budget_usd}
                    onChange={(e) => setDraft({ ...draft, weekly_budget_usd: Number(e.target.value) || 0 })}
                  />
                </Field>
                <Field label="每月 USD">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={inputCls}
                    value={draft.monthly_budget_usd}
                    onChange={(e) => setDraft({ ...draft, monthly_budget_usd: Number(e.target.value) || 0 })}
                  />
                </Field>
              </div>
            </div>

            <div className="rs-budget">
              <div className="rs-budget-h">
                <h4>雲服務預算</h4>
                <span>今日已用 {fmtUsd(agent.cloud_cost_usd ?? agent.metrics?.cloud_spent_usd ?? 0)} · Docker＋阿里雲</span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Field label="每日 USD">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={inputCls}
                    value={draft.cloud_daily_budget_usd}
                    onChange={(e) => setDraft({ ...draft, cloud_daily_budget_usd: Number(e.target.value) || 0 })}
                  />
                </Field>
                <Field label="每週 USD">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={inputCls}
                    value={draft.cloud_weekly_budget_usd}
                    onChange={(e) => setDraft({ ...draft, cloud_weekly_budget_usd: Number(e.target.value) || 0 })}
                  />
                </Field>
                <Field label="每月 USD">
                  <input
                    type="number"
                    min={0}
                    step={0.1}
                    className={inputCls}
                    value={draft.cloud_monthly_budget_usd}
                    onChange={(e) => setDraft({ ...draft, cloud_monthly_budget_usd: Number(e.target.value) || 0 })}
                  />
                </Field>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-white/[0.08] bg-[#141416] p-3">
            <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#8a8f98]">SLA／告警</h4>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <Field label="SLA 延遲 ms" hint="0=不檢查">
                <input
                  type="number"
                  min={0}
                  className={inputCls}
                  value={draft.sla_latency_ms}
                  onChange={(e) => setDraft({ ...draft, sla_latency_ms: Number(e.target.value) || 0 })}
                />
              </Field>
              <div className="flex flex-wrap content-end gap-3">
                <label className="flex items-center gap-2 text-[12px] text-[#d0d6e0]">
                  <input
                    type="checkbox"
                    checked={draft.alert_on_error}
                    onChange={(e) => setDraft({ ...draft, alert_on_error: e.target.checked })}
                  />
                  錯誤時告警
                </label>
                <label className="flex items-center gap-2 text-[12px] text-[#d0d6e0]">
                  <input
                    type="checkbox"
                    checked={draft.alert_on_budget}
                    onChange={(e) => setDraft({ ...draft, alert_on_budget: e.target.checked })}
                  />
                  預算告警
                </label>
                <label className="flex items-center gap-2 text-[12px] text-[#d0d6e0]">
                  <input
                    type="checkbox"
                    checked={draft.alert_on_sla}
                    onChange={(e) => setDraft({ ...draft, alert_on_sla: e.target.checked })}
                  />
                  SLA 逾時告警
                </label>
                <label className="flex items-center gap-2 text-[12px] text-[#d0d6e0]">
                  <input
                    type="checkbox"
                    checked={draft.always_require_review}
                    onChange={(e) => setDraft({ ...draft, always_require_review: e.target.checked })}
                  />
                  產出一律送審查
                </label>
              </div>
            </div>
          </div>
        </div>
      </section>
      </div>
      </div>
    </div>
  );
}

interface CreateRoleModalProps {
  catalog: AgentCatalogMeta | undefined;
  agents: RoleAgent[];
  cloneFrom?: RoleAgent | null;
  onClose: () => void;
  onCreate: (payload: Record<string, unknown>) => Promise<void>;
}

export function CreateRoleModal({ catalog, agents, cloneFrom, onClose, onCreate }: CreateRoleModalProps) {
  const presets = catalog?.role_presets ?? [];
  const [id, setId] = useState(cloneFrom ? `copy_${cloneFrom.id}` : '');
  const [name, setName] = useState(cloneFrom ? `${cloneFrom.name}（副本）` : '');
  const [level, setLevel] = useState(cloneFrom?.level ?? 3);
  const [category, setCategory] = useState(cloneFrom?.category || 'management');
  const [prompt, setPrompt] = useState(cloneFrom?.system_prompt ?? '');
  const [responsibilities, setResponsibilities] = useState((cloneFrom?.responsibilities ?? []).join('\n'));
  const [reportingTo, setReportingTo] = useState(cloneFrom?.reporting_to ?? '');
  const [tier, setTier] = useState(cloneFrom?.default_tier || 'routine');
  const [description, setDescription] = useState(cloneFrom?.description ?? '');
  const [model, setModel] = useState(cloneFrom?.preferred_model ?? '');
  const [provider, setProvider] = useState(cloneFrom?.preferred_provider ?? '');
  const [maxOutput, setMaxOutput] = useState(cloneFrom?.max_output_tokens ?? 4096);
  const [contextWindow, setContextWindow] = useState(cloneFrom?.context_window ?? 0);
  const [budget, setBudget] = useState(cloneFrom?.daily_budget_usd ?? 0);
  const [cloudBudget, setCloudBudget] = useState(cloneFrom?.cloud_daily_budget_usd ?? 0);
  const [routing, setRouting] = useState(cloneFrom?.routing_strategy || 'quality_first');
  const [parallel, setParallel] = useState(cloneFrom?.max_parallel_work ?? 2);
  const [language, setLanguage] = useState(cloneFrom?.language || 'zh-TW');
  const [priority, setPriority] = useState(cloneFrom?.priority ?? 3);
  const [requireReview, setRequireReview] = useState(cloneFrom?.always_require_review === true);
  const [onCall, setOnCall] = useState(cloneFrom?.on_call === true);
  const [mainlandOnly, setMainlandOnly] = useState(cloneFrom?.mainland_only === true);
  const [humanApproval, setHumanApproval] = useState(cloneFrom?.require_human_approval === true);
  const [tags, setTags] = useState((cloneFrom?.tags ?? []).join(', '));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [presetId, setPresetId] = useState(cloneFrom?.id ?? '');

  const applyPreset = (preset: RolePreset) => {
    setPresetId(preset.id);
    setName(preset.name);
    setId(preset.id);
    setLevel(preset.level);
    setCategory(preset.category);
    setPrompt(preset.system_prompt);
    setResponsibilities((preset.responsibilities ?? []).join('\n'));
    setReportingTo(preset.reporting_to ?? '');
    setTier(preset.default_tier);
    setDescription(preset.hint ?? '');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto apple-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{cloneFrom ? `複製「${cloneFrom.name}」` : '新增自定義角色'}</h3>
          <button type="button" className="text-[12px] text-[#8a8f98]" onClick={onClose}>
            關閉
          </button>
        </div>
        {error && <p className="mb-2 text-[12px] text-red-300">{error}</p>}
        {presets.length > 0 && !cloneFrom && (
          <div className="mb-3">
            <p className="mb-1 text-[10px] uppercase tracking-wider text-[#62666d]">快速模板</p>
            <div className="flex flex-wrap gap-1">
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  title={p.hint}
                  onClick={() => applyPreset(p)}
                  className={`rounded border px-2 py-1 text-[11px] ${
                    presetId === p.id
                      ? 'border-[#007AFF]/40 bg-[#007AFF]/15 text-[#64D2FF]'
                      : 'border-white/[0.08] text-[#8a8f98]'
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="space-y-2">
          <input className={inputCls} placeholder="顯示名稱（如 量化交易員）" value={name} onChange={(e) => setName(e.target.value)} />
          <input className={inputCls} placeholder="id 建議英文（自動加 custom_ 前綴）" value={id} onChange={(e) => setId(e.target.value)} />
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <select className={inputCls} value={level} onChange={(e) => setLevel(Number(e.target.value))}>
              {(catalog?.levels ?? []).map((lv) => (
                <option key={lv.level} value={lv.level}>
                  {lv.label}
                </option>
              ))}
            </select>
            <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
              {(catalog?.categories ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
            <select className={inputCls} value={tier} onChange={(e) => setTier(e.target.value)}>
              {(catalog?.tiers ?? Object.entries(TIER_LABEL).map(([tid, label]) => ({ id: tid, label }))).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            <select className={inputCls} value={reportingTo} onChange={(e) => setReportingTo(e.target.value)}>
              <option value="">無上級</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <textarea
            className={inputCls}
            rows={5}
            placeholder="系統提示詞（角色設定）"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <textarea
            className={inputCls}
            rows={3}
            placeholder="職責，一行一項"
            value={responsibilities}
            onChange={(e) => setResponsibilities(e.target.value)}
          />
          <input
            className={inputCls}
            placeholder="一句話職責（目錄摘要）"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <select
              className={inputCls}
              value={provider}
              onChange={(e) => {
                const next = e.target.value;
                const group = (catalog?.models_by_provider ?? []).find((g) => g.route_id === next);
                setProvider(next);
                if (next && group && !group.models.includes(model)) {
                  setModel(group.models[0] || '');
                }
              }}
            >
              <option value="">API：全域預設</option>
              {(catalog?.api_routes ?? []).map((route) => (
                <option key={route.id} value={route.id}>
                  {routeOptionLabel(route)}
                </option>
              ))}
            </select>
            <select className={inputCls} value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">模型：該 API 預設</option>
              {(catalog?.models_by_provider ?? [])
                .filter((g) => !provider || g.route_id === provider)
                .flatMap((g) => g.models.map((mid) => ({ group: g.name, mid })))
                .map((row) => (
                  <option key={`${row.group}-${row.mid}`} value={row.mid}>
                    {row.mid}
                  </option>
                ))}
            </select>
            <input
              className={inputCls}
              type="number"
              min={256}
              max={128000}
              placeholder="輸出 Token"
              value={maxOutput}
              onChange={(e) => setMaxOutput(Number(e.target.value) || 4096)}
            />
            <input
              className={inputCls}
              type="number"
              min={0}
              max={2000000}
              placeholder="上下文 Token（0=不截斷）"
              value={contextWindow}
              onChange={(e) => setContextWindow(Number(e.target.value) || 0)}
            />
            <select className={inputCls} value={routing} onChange={(e) => setRouting(e.target.value)}>
              {(catalog?.routing_strategies ?? [{ id: 'quality_first', label: '品質優先' }]).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
            <input
              className={inputCls}
              type="number"
              min={0}
              step={0.1}
              placeholder="AI 日預算 USD"
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value) || 0)}
            />
            <input
              className={inputCls}
              type="number"
              min={0}
              step={0.1}
              placeholder="雲服務日預算 USD"
              value={cloudBudget}
              onChange={(e) => setCloudBudget(Number(e.target.value) || 0)}
            />
            <input
              className={inputCls}
              type="number"
              min={1}
              max={16}
              placeholder="並行"
              value={parallel}
              onChange={(e) => setParallel(Number(e.target.value) || 2)}
            />
            <select className={inputCls} value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="zh-TW">繁中</option>
              <option value="zh-CN">簡中</option>
              <option value="en">English</option>
            </select>
            <input
              className={inputCls}
              type="number"
              min={1}
              max={5}
              placeholder="優先級"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value) || 3)}
            />
            <label className="flex items-center gap-2 text-[11px] text-[#d0d6e0]">
              <input type="checkbox" checked={requireReview} onChange={(e) => setRequireReview(e.target.checked)} />
              一律送審查
            </label>
            <label className="flex items-center gap-2 text-[11px] text-[#d0d6e0]">
              <input type="checkbox" checked={onCall} onChange={(e) => setOnCall(e.target.checked)} />
              值班
            </label>
            <label className="flex items-center gap-2 text-[11px] text-[#d0d6e0]">
              <input type="checkbox" checked={humanApproval} onChange={(e) => setHumanApproval(e.target.checked)} />
              需人工核准
            </label>
            <label className="flex items-center gap-2 text-[11px] text-[#d0d6e0]">
              <input type="checkbox" checked={mainlandOnly} onChange={(e) => setMainlandOnly(e.target.checked)} />
              僅國內模型
            </label>
          </div>
          <input className={inputCls} placeholder="標籤，逗號分隔" value={tags} onChange={(e) => setTags(e.target.value)} />
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className="rounded border border-white/[0.08] px-3 py-1.5 text-[12px] text-[#8a8f98]" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            disabled={busy || !name.trim()}
            className="rounded border border-[#007AFF]/40 bg-[#007AFF]/15 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40"
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                await onCreate({
                  id: id.trim() || name.trim(),
                  name: name.trim(),
                  level,
                  category,
                  default_tier: tier,
                  system_prompt: prompt,
                  responsibilities: responsibilities.split('\n').map((s) => s.trim()).filter(Boolean),
                  reporting_to: reportingTo || agents.find((a) => a.level < level)?.id || 'manager',
                  clone_from: cloneFrom?.id,
                  description,
                  preferred_model: model,
                  preferred_provider: provider,
                  max_output_tokens: maxOutput,
                  context_window: contextWindow,
                  daily_budget_usd: budget,
                  weekly_budget_usd: cloneFrom?.weekly_budget_usd ?? 0,
                  monthly_budget_usd: cloneFrom?.monthly_budget_usd ?? 0,
                  cloud_daily_budget_usd: cloudBudget,
                  cloud_weekly_budget_usd: cloneFrom?.cloud_weekly_budget_usd ?? 0,
                  cloud_monthly_budget_usd: cloneFrom?.cloud_monthly_budget_usd ?? 0,
                  routing_strategy: routing,
                  max_parallel_work: parallel,
                  language,
                  priority,
                  always_require_review: requireReview,
                  on_call: onCall,
                  require_human_approval: humanApproval,
                  mainland_only: mainlandOnly,
                  tags: tags.split(',').map((s) => s.trim()).filter(Boolean),
                });
                onClose();
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? '建立中…' : cloneFrom ? '建立副本' : '建立'}
          </button>
        </div>
      </div>
    </div>
  );
}
