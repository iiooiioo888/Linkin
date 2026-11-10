/**
 * 模型／Token section：供應商、模型、價目與輸出上限。
 */
import {
  ROUTING_LABEL,
  TIER_LABEL,
  fmtPerMillion,
  fmtRate,
  lookupRateCard,
  rateOptionLabel,
  routeDisplayName,
} from '../../../lib/agentUi';
import { modelsForRoute } from '../../../lib/llmCatalog';
import { navPathForTab } from '../../../lib/monitorTabs';
import type { AgentCatalogMeta } from '../../../types';
import { Field, TokenSlider, inputCls, routeOptionLabel, tokenHint } from '../fields';
import type { DraftUpdater, RoleSettingsDraft } from '../types';

interface ModelSectionProps {
  catalog: AgentCatalogMeta | undefined;
  draft: RoleSettingsDraft;
  setDraft: DraftUpdater;
}

export default function ModelSection({ catalog, draft, setDraft }: ModelSectionProps) {
  const tiers = catalog?.tiers ?? Object.entries(TIER_LABEL).map(([id, label]) => ({ id, label }));
  const routing = catalog?.routing_strategies ?? Object.entries(ROUTING_LABEL).map(([id, label]) => ({ id, label }));
  const selectedHint = tokenHint(draft.preferred_model, catalog?.model_token_hints);
  const outputMax = selectedHint?.max_output ?? 32768;
  const contextMax = selectedHint?.max_context ?? 2_000_000;
  const activeRoute =
    (catalog?.api_routes ?? []).find((r) => r.id === draft.preferred_provider) ||
    catalog?.api_routes?.find((r) => r.is_default);
  const defaultRoute = catalog?.api_routes?.find((r) => r.is_default);
  const selectedRate = lookupRateCard(
    draft.preferred_model || activeRoute?.model,
    catalog?.model_rate_cards,
  );
  const modelStatus = [
    routeDisplayName(activeRoute) || '全域預設',
    draft.preferred_model || 'API 預設模型',
    selectedRate
      ? `USD ${fmtPerMillion(selectedRate.input)} / ${fmtPerMillion(selectedRate.output)} · +${Math.max(0, (selectedRate.items?.length ?? 2) - 2)} 收費項`
      : null,
    `輸出 ${draft.max_output_tokens.toLocaleString()}`,
    draft.context_window > 0 ? `上下文 ${draft.context_window.toLocaleString()}` : '上下文不截斷',
  ]
    .filter(Boolean)
    .join(' · ');

  return (
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
          <p className="md:col-span-2 lg:col-span-3 rounded-xl border border-[color-mix(in_srgb,var(--console-amber)_25%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--console-amber)]">
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
              const routeModels = modelsForRoute(catalog?.models_by_provider ?? [], next);
              const nextModel =
                next && routeModels.length > 0 && !routeModels.includes(draft.preferred_model)
                  ? routeModels[0] || ''
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
        <Field
          label="指定模型"
          hint={
            selectedRate
              ? `輸入 ${fmtPerMillion(selectedRate.input)} · 輸出 ${fmtPerMillion(selectedRate.output)} · 另 ${(selectedRate.items ?? []).length} 項`
              : '依上方供應商列出可用模型；空白=該 API 預設'
          }
        >
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
                          {rateOptionLabel(id, catalog?.model_rate_cards)}
                        </option>
                      ))}
                    </optgroup>
                  ))
              : (catalog?.allowed_models ?? []).map((id) => (
                  <option key={id} value={id}>
                    {rateOptionLabel(id, catalog?.model_rate_cards)}
                  </option>
                ))}
          </select>
        </Field>
        {selectedRate ? (
          <div className="md:col-span-2 lg:col-span-3 rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-[#62666d]">價目 USD / 1M tokens</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {(selectedRate.items ?? []).map((item) => (
                <span
                  key={item.id}
                  className="rounded-md bg-white/[0.04] px-2 py-0.5 font-mono text-[11px] text-[#d0d6e0]"
                >
                  {item.label} {fmtRate(item.usd_per_1m, item.unit)}
                </span>
              ))}
            </div>
          </div>
        ) : null}
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
  );
}
