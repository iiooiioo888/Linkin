/**
 * 角色預算摘要：AI（LLM API）與雲服務（Docker＋阿里雲）分開顯示已用／上限／剩餘。
 */
import { useTranslation } from 'react-i18next';
import type { RoleAgent } from '../types';
import { blankMetrics, fmtUsd } from '../lib/agentUi';

function limitLabel(limit: number | undefined, unlimited: string): string {
  const n = limit ?? 0;
  return n > 0 ? fmtUsd(n) : unlimited;
}

function spentPct(spent: number, limit: number): number {
  if (limit <= 0) return 0;
  return Math.max(0, Math.min(100, (spent / limit) * 100));
}

function BudgetRow({
  label,
  spent,
  limit,
  remaining,
  over,
  unlimited,
}: {
  label: string;
  spent: number;
  limit: number;
  remaining: number | null | undefined;
  over?: boolean;
  unlimited: string;
}) {
  const hasLimit = limit > 0;
  const pct = spentPct(spent, limit);
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between gap-2 text-[10px]">
        <span className="text-[var(--console-sub)]">{label}</span>
        <span className={`font-mono tabular-nums ${over ? 'text-[var(--console-amber)]' : 'text-[var(--console-ink)]'}`}>
          {fmtUsd(spent)}
          {hasLimit ? (
            <span className="text-[var(--console-faint)]"> / {limitLabel(limit, unlimited)}</span>
          ) : (
            <span className="text-[var(--console-faint)]"> · {unlimited}</span>
          )}
        </span>
      </div>
      {hasLimit ? (
        <>
          <div className="h-1 overflow-hidden rounded-full bg-[var(--console-card)]">
            <div
              className="h-full transition-all"
              style={{
                width: `${pct}%`,
                background: over ? 'var(--console-amber)' : pct >= 90 ? '#e5484d' : 'var(--console-blue)',
              }}
            />
          </div>
          <p className="text-[9px] text-[var(--console-faint)]">
            {over
              ? '已超預算'
              : remaining != null
                ? `剩餘 ${fmtUsd(remaining)}`
                : null}
          </p>
        </>
      ) : null}
    </div>
  );
}

export function RoleBudgetSummary({
  agent,
  compact = false,
}: {
  agent: RoleAgent;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const m = agent.metrics ?? blankMetrics();
  const api = m.api_spent_usd ?? agent.api_cost_usd ?? 0;
  const cloud = m.cloud_spent_usd ?? agent.cloud_cost_usd ?? 0;
  const aiDaily = agent.daily_budget_usd ?? 0;
  const cloudDaily = agent.cloud_daily_budget_usd ?? 0;
  const unlimited = t('roles.budgetUnlimited');

  if (compact) {
    const aiText =
      aiDaily > 0
        ? `${fmtUsd(api)} / ${fmtUsd(aiDaily)}`
        : `${fmtUsd(api)} · ${unlimited}`;
    const cloudText =
      cloudDaily > 0
        ? `${fmtUsd(cloud)} / ${fmtUsd(cloudDaily)}`
        : `${fmtUsd(cloud)} · ${unlimited}`;
    return (
      <div className="space-y-1.5 rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-2.5 py-2">
        <p className="text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
          {t('roles.budgetSummary')}
        </p>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px]">
          <span>
            <span className="text-[var(--console-faint)]">{t('roles.budgetAi')} </span>
            <span className={`font-mono ${agent.ai_budget_over ? 'text-[var(--console-amber)]' : ''}`}>{aiText}</span>
          </span>
          <span>
            <span className="text-[var(--console-faint)]">{t('roles.budgetCloud')} </span>
            <span className={`font-mono ${agent.cloud_budget_over ? 'text-[var(--console-amber)]' : ''}`}>{cloudText}</span>
          </span>
        </div>
        {(agent.budget_over || (m.budget_alerts ?? 0) > 0) ? (
          <p className="text-[9px] text-[var(--console-amber)]">{t('roles.budgetOver')}</p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rd-sec">
      <div className="rd-tt">{t('roles.budgetSummary')}</div>
      <div className="space-y-3">
        <div className="rd-budget-block">
          <div className="rd-budget-h">
            <strong>{t('roles.budgetAi')}</strong>
            <span>{t('roles.budgetAiHint')}</span>
          </div>
          <BudgetRow
            label={t('roles.budgetDaily')}
            spent={api}
            limit={aiDaily}
            remaining={agent.ai_budget_remaining_usd}
            over={agent.ai_budget_over}
            unlimited={unlimited}
          />
          {!compact && (agent.weekly_budget_usd ?? 0) > 0 ? (
            <p className="mt-1 text-[9px] text-[var(--console-faint)]">
              {t('roles.budgetWeeklyMonthly')}: {limitLabel(agent.weekly_budget_usd, unlimited)} / {limitLabel(agent.monthly_budget_usd, unlimited)}
            </p>
          ) : null}
        </div>
        <div className="rd-budget-block">
          <div className="rd-budget-h">
            <strong>{t('roles.budgetCloud')}</strong>
            <span>{t('roles.budgetCloudHint')}</span>
          </div>
          <BudgetRow
            label={t('roles.budgetDaily')}
            spent={cloud}
            limit={cloudDaily}
            remaining={agent.cloud_budget_remaining_usd}
            over={agent.cloud_budget_over}
            unlimited={unlimited}
          />
          {!compact && (agent.cloud_weekly_budget_usd ?? 0) > 0 ? (
            <p className="mt-1 text-[9px] text-[var(--console-faint)]">
              {t('roles.budgetWeeklyMonthly')}: {limitLabel(agent.cloud_weekly_budget_usd, unlimited)} / {limitLabel(agent.cloud_monthly_budget_usd, unlimited)}
            </p>
          ) : null}
        </div>
        {(agent.budget_over || (m.budget_alerts ?? 0) > 0) ? (
          <p className="text-[10px] text-[var(--console-amber)]">
            {t('roles.budgetAlertCount', { count: m.budget_alerts ?? 0 })}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export interface AccountBudgetSummary {
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

export function AccountBudgetBanner({ summary }: { summary?: AccountBudgetSummary | null }) {
  const { t } = useTranslation();
  if (!summary) return null;
  const hub = summary.hub_daily;
  const credits = summary.linkin_credits;
  if (!hub && !credits) return null;

  const hubPct =
    hub && hub.daily_limit_usd > 0
      ? Math.min(100, (hub.spent_today_usd / hub.daily_limit_usd) * 100)
      : 0;

  return (
    <div className="mb-3 grid gap-2 sm:grid-cols-2">
      {hub ? (
        <div className="rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
            {t('roles.accountHubBudget')}
          </p>
          <p className="mt-1 font-mono text-[12px] text-[var(--console-ink)]">
            {fmtUsd(hub.spent_today_usd)}
            <span className="text-[10px] text-[var(--console-faint)]">
              {' '}/ {hub.daily_limit_usd > 0 ? fmtUsd(hub.daily_limit_usd) : t('roles.budgetUnlimited')}
            </span>
          </p>
          {hub.daily_limit_usd > 0 ? (
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-[var(--console-sidebar)]">
              <div
                className="h-full bg-[var(--console-blue)]"
                style={{
                  width: `${hubPct}%`,
                  background: hubPct >= 90 ? '#e5484d' : 'var(--console-blue)',
                }}
              />
            </div>
          ) : null}
          <p className="mt-1 text-[9px] text-[var(--console-faint)]">{t('roles.accountHubHint')}</p>
        </div>
      ) : null}
      {credits ? (
        <div className="rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2">
          <p className="text-[9px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
            {t('roles.accountLinkinCredits')}
          </p>
          <p className="mt-1 font-mono text-[12px] text-[var(--console-ink)]">
            {credits.balance_credits.toLocaleString()}
            <span className="text-[10px] text-[var(--console-faint)]"> {t('roles.creditsUnit')}</span>
          </p>
          {credits.monthly_quota_credits > 0 ? (
            <p className="mt-1 text-[9px] text-[var(--console-faint)]">
              {t('roles.creditsMonthlyUsed', {
                used: credits.monthly_used_credits.toLocaleString(),
                quota: credits.monthly_quota_credits.toLocaleString(),
              })}
            </p>
          ) : null}
          <p className="mt-1 text-[9px] text-[var(--console-faint)]">{t('roles.accountCreditsHint')}</p>
        </div>
      ) : null}
    </div>
  );
}
