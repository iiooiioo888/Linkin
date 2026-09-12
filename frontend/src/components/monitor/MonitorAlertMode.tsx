/**
 * 監控模式全螢幕覆蓋 — 突顯異常並可點擊跳轉。
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { MonitorTab } from '../AppShell';
import { useMonitorStore } from '../../stores/monitorStore';
import { fmtCredits } from '../../lib/billingUi';

export interface MonitorAlertModeProps {
  open: boolean;
  onClose: () => void;
  onJump: (tab: MonitorTab, detail?: string) => void;
  unhealthyKeysCount?: number;
}

type AlertItem = {
  id: string;
  tone: 'danger' | 'warn' | 'info';
  title: string;
  detail: string;
  tab: MonitorTab;
  detailId?: string;
};

export default function MonitorAlertMode({
  open,
  onClose,
  onJump,
  unhealthyKeysCount = 0,
}: MonitorAlertModeProps) {
  const { t } = useTranslation();
  const dashboard = useMonitorStore((s) => s.dashboard);
  const billing = useMonitorStore((s) => s.billing);
  const agents = useMonitorStore((s) => s.agents);

  const alerts = useMemo(() => {
    const items: AlertItem[] = [];
    const stats = (dashboard?.stats ?? {}) as Record<string, number | undefined>;
    const failed = Number(stats.failed ?? stats.failed_tasks ?? 0);
    const running = Number(stats.running ?? stats.running_tasks ?? 0);
    if (failed > 0) {
      items.push({
        id: 'failed-tasks',
        tone: 'danger',
        title: t('monitorAlert.failedTasks', { count: failed }),
        detail: t('monitorAlert.failedTasksHint'),
        tab: 'tasks',
      });
    }
    const dockerRate = billing?.docker?.total_hourly_rate ?? 0;
    if (dockerRate > 500) {
      items.push({
        id: 'high-docker',
        tone: 'warn',
        title: t('monitorAlert.highDocker'),
        detail: `${fmtCredits(dockerRate)}/h`,
        tab: 'credits',
      });
    }
    if (unhealthyKeysCount > 0) {
      items.push({
        id: 'unhealthy-keys',
        tone: 'danger',
        title: t('monitorAlert.unhealthyKeys', { count: unhealthyKeysCount }),
        detail: t('monitorAlert.unhealthyKeysHint'),
        tab: 'credits',
        detailId: 'contributor',
      });
    }
    const busyAgents = (agents?.agents ?? []).filter((a) => a.status === 'busy' && (a.metrics?.budget_alerts ?? 0) > 0);
    if (busyAgents.length > 0) {
      items.push({
        id: 'agent-budget',
        tone: 'warn',
        title: t('monitorAlert.agentBudget', { count: busyAgents.length }),
        detail: busyAgents.map((a) => a.name).slice(0, 3).join(' · '),
        tab: 'agents',
        detailId: busyAgents[0]?.id,
      });
    }
    if (running > 8) {
      items.push({
        id: 'high-load',
        tone: 'info',
        title: t('monitorAlert.highLoad', { count: running }),
        detail: t('monitorAlert.highLoadHint'),
        tab: 'live',
      });
    }
    return items;
  }, [agents?.agents, billing?.docker?.total_hourly_rate, dashboard?.stats, t, unhealthyKeysCount]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex flex-col bg-[var(--console-bg)]/95 backdrop-blur-md"
      data-testid="monitor-alert-mode"
      role="dialog"
      aria-modal="true"
      aria-label={t('monitorAlert.title')}
    >
      <header className="flex shrink-0 items-center justify-between border-b border-[var(--console-line)] px-4 py-3 sm:px-6">
        <div>
          <h2 className="text-[15px] font-semibold text-[var(--console-ink)]">{t('monitorAlert.title')}</h2>
          <p className="text-[11px] text-[var(--console-sub)]">{t('monitorAlert.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-white/[0.08] px-3 py-1.5 text-[11px] text-[var(--console-sub)] hover:bg-white/[0.04]"
        >
          {t('monitorAlert.exit')}
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {alerts.length === 0 ? (
          <p className="text-center text-[13px] text-[var(--console-sub)]">{t('monitorAlert.allClear')}</p>
        ) : (
          <ul className="mx-auto grid max-w-2xl gap-3">
            {alerts.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => {
                    onJump(a.tab, a.detailId);
                    onClose();
                  }}
                  className={`flex w-full flex-col gap-1 rounded-xl border px-4 py-3 text-left transition-colors hover:bg-white/[0.03] ${
                    a.tone === 'danger'
                      ? 'border-[color-mix(in_srgb,var(--console-danger)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-danger)_8%,transparent)]'
                      : a.tone === 'warn'
                        ? 'border-[color-mix(in_srgb,var(--console-amber)_35%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_8%,transparent)]'
                        : 'border-[var(--console-line)] bg-[var(--console-card)]'
                  }`}
                >
                  <span className="text-[13px] font-semibold text-[var(--console-ink)]">{a.title}</span>
                  <span className="text-[11px] text-[var(--console-sub)]">{a.detail}</span>
                  <span className="text-[10px] console-status-accent">{t('monitorAlert.jump')} →</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
