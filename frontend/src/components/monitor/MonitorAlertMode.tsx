/**
 * 監控模式全螢幕覆蓋 — 突顯異常並可點擊跳轉。
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { MonitorTab } from '../AppShell';
import { useMonitorStore } from '../../stores/monitorStore';
import { fmtCredits } from '../../lib/billingUi';
import '../ui/monitor/monitor.css';

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
        tab: 'ops',
      });
    }
    if (unhealthyKeysCount > 0) {
      items.push({
        id: 'unhealthy-keys',
        tone: 'danger',
        title: t('monitorAlert.unhealthyKeys', { count: unhealthyKeysCount }),
        detail: t('monitorAlert.unhealthyKeysHint'),
        tab: 'llm',
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
      className="mon-alert-overlay"
      data-testid="monitor-alert-mode"
      role="dialog"
      aria-modal="true"
      aria-label={t('monitorAlert.title')}
    >
      <header className="mon-alert-overlay__head">
        <div>
          <h2 className="text-[15px] font-semibold text-[var(--console-ink)]">{t('monitorAlert.title')}</h2>
          <p className="text-[11px] text-[var(--console-sub)]">{t('monitorAlert.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mon-alert-btn"
        >
          {t('monitorAlert.exit')}
        </button>
      </header>
      <div className="mon-alert-overlay__body">
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
                  className={`mon-alert-card${a.tone === 'danger' ? ' mon-alert-card--danger' : a.tone === 'warn' ? ' mon-alert-card--warn' : ''}`}
                >
                  <span className="text-[13px] font-semibold text-[var(--console-ink)]">{a.title}</span>
                  <span className="text-[11px] text-[var(--console-sub)]">{a.detail}</span>
                  <span className="text-[10px] text-[var(--console-accent)]">{t('monitorAlert.jump')} →</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
