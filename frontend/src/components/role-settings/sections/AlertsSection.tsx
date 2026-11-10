/**
 * 預算／告警／監控 section：AI 與雲服務預算分開控管，SLA 與告警。
 */
import { fmtUsd } from '../../../lib/agentUi';
import type { RoleAgent } from '../../../types';
import { Field, inputCls } from '../fields';
import type { DraftUpdater, RoleSettingsDraft } from '../types';

interface AlertsSectionProps {
  agent: RoleAgent;
  draft: RoleSettingsDraft;
  setDraft: DraftUpdater;
}

export default function AlertsSection({ agent, draft, setDraft }: AlertsSectionProps) {
  return (
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

        <div className="rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-3">
          <h4 className="mb-2 text-[11px] font-semibold text-[var(--console-faint)]">SLA／告警</h4>
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
              <label className="flex items-center gap-2 text-[12px] text-[var(--console-sub)]">
                <input
                  type="checkbox"
                  checked={draft.alert_on_error}
                  onChange={(e) => setDraft({ ...draft, alert_on_error: e.target.checked })}
                />
                錯誤時告警
              </label>
              <label className="flex items-center gap-2 text-[12px] text-[var(--console-sub)]">
                <input
                  type="checkbox"
                  checked={draft.alert_on_budget}
                  onChange={(e) => setDraft({ ...draft, alert_on_budget: e.target.checked })}
                />
                預算告警
              </label>
              <label className="flex items-center gap-2 text-[12px] text-[var(--console-sub)]">
                <input
                  type="checkbox"
                  checked={draft.alert_on_sla}
                  onChange={(e) => setDraft({ ...draft, alert_on_sla: e.target.checked })}
                />
                SLA 逾時告警
              </label>
              <label className="flex items-center gap-2 text-[12px] text-[var(--console-sub)]">
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
  );
}
