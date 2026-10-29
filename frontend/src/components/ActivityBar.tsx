/**
 * ActivityBar — Agent Desk 頂層活動。
 * 桌面：左側垂直欄（工作／觀測／計算／供給／資產／世界／設定）
 * 行動：底部 Tab（工作／觀測／更多）；更多內含計算／供給／資產／世界／設定
 */
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  DESK_ACTIVITIES,
  normalizeDeskActivity,
  type ActivityKey,
  type DeskActivityKey,
} from '../lib/monitorTabs';
import { MOBILE_MORE_ACTIVITIES, MOBILE_PRIMARY_ACTIVITIES } from '../lib/mobileShell';
import type { MonitorTab, ViewKey } from './AppShell';

interface ActivityBarProps {
  activity: ActivityKey;
  activeView?: ViewKey;
  monitorTab?: MonitorTab;
  onActivityChange: (activity: ActivityKey) => void;
  placement?: 'sidebar' | 'bottom';
  onMobileTasks?: () => void;
  onMobileUsage?: () => void;
  onMobileConsoleTab?: (tab: MonitorTab) => void;
}

function WorkIcon({ active }: { active: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M3 4.5a1.5 1.5 0 011.5-1.5h9A1.5 1.5 0 0115 4.5v6A1.5 1.5 0 0113.5 12H7l-3 2.5V4.5z"
        stroke="currentColor"
        strokeWidth="1.3"
        fill={active ? 'currentColor' : 'none'}
        fillOpacity={active ? 0.15 : 0}
      />
    </svg>
  );
}

function ObserveIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="2" y="3" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M6 15h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function ComputeIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path d="M3 14V8M7.5 14V5M12 14V10M16.5 14V3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function SupplyIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M4.5 12.5a3.5 3.5 0 010-7 4.2 4.2 0 018.1-1.2A3.2 3.2 0 0114.5 12.5H4.5z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AssetsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="3" y="4" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
      <path d="M6 8h6M6 11h4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function WorldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M9 2.4l6.2 3.2v6.8L9 15.6 2.8 12.4V5.6L9 2.4z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M9 2.4v13.2M2.8 5.6L9 8.8l6.2-3.2" stroke="currentColor" strokeWidth="1.2" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <circle cx="9" cy="9" r="2.2" stroke="currentColor" strokeWidth="1.3" />
      <path
        d="M9 2.5v2M9 13.5v2M2.5 9h2M13.5 9h2M4.2 4.2l1.4 1.4M12.4 12.4l1.4 1.4M13.8 4.2l-1.4 1.4M5.6 12.4l-1.4 1.4"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoreIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <circle cx="4.5" cy="9" r="1.2" fill="currentColor" />
      <circle cx="9" cy="9" r="1.2" fill="currentColor" />
      <circle cx="13.5" cy="9" r="1.2" fill="currentColor" />
    </svg>
  );
}

function deskIcon(key: DeskActivityKey, active: boolean): ReactNode {
  switch (key) {
    case 'work':
      return <WorkIcon active={active} />;
    case 'observe':
      return <ObserveIcon />;
    case 'compute':
      return <ComputeIcon />;
    case 'supply':
      return <SupplyIcon />;
    case 'assets':
      return <AssetsIcon />;
    case 'world':
      return <WorldIcon />;
    case 'settings':
      return <SettingsIcon />;
    default:
      return <ObserveIcon />;
  }
}

type BarItem = { key: DeskActivityKey; label: string; icon: (active: boolean) => ReactNode };

function ActivityButtons({
  items,
  activity,
  onActivityChange,
  placement,
}: {
  items: BarItem[];
  activity: ActivityKey;
  onActivityChange: (activity: ActivityKey) => void;
  placement: 'sidebar' | 'bottom';
}) {
  const isBottom = placement === 'bottom';
  const current = normalizeDeskActivity(activity);

  return (
    <>
      {items.map((item) => {
        const active = current === item.key;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onActivityChange(item.key)}
            className={
              isBottom
                ? `activity-tab-bottom touch-manipulation ${active ? 'is-active' : ''}`
                : `activity-rail-btn touch-manipulation ${active ? 'is-active' : ''}`
            }
            title={item.label}
            aria-label={item.label}
            aria-current={active ? 'page' : undefined}
          >
            {isBottom ? (
              <>
                <span className="activity-tab-bottom__icon">{item.icon(active)}</span>
                <span className="activity-tab-bottom__label">{item.label}</span>
              </>
            ) : (
              item.icon(active)
            )}
          </button>
        );
      })}
    </>
  );
}

function MobileBottomBar({
  activity,
  onActivityChange,
}: {
  activity: ActivityKey;
  activeView?: ViewKey;
  monitorTab?: MonitorTab;
  onActivityChange: (activity: ActivityKey) => void;
  onMobileTasks?: () => void;
  onMobileUsage?: () => void;
  onMobileConsoleTab?: (tab: MonitorTab) => void;
}) {
  const { t } = useTranslation();
  const [moreOpen, setMoreOpen] = useState(false);
  const current = normalizeDeskActivity(activity) as DeskActivityKey;
  const moreActive = (MOBILE_MORE_ACTIVITIES as readonly string[]).includes(current);

  const labelFor = (key: DeskActivityKey) => {
    const row = DESK_ACTIVITIES.find((a) => a.key === key);
    return t(`nav.${key}`, { defaultValue: row?.label ?? key });
  };

  return (
    <>
      <nav className="activity-bar-bottom md:hidden" aria-label="主活動">
        {MOBILE_PRIMARY_ACTIVITIES.map((key) => {
          const active = current === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onActivityChange(key)}
              className={`activity-tab-bottom touch-manipulation ${active ? 'is-active' : ''}`}
              aria-current={active ? 'page' : undefined}
            >
              <span className="activity-tab-bottom__icon">{deskIcon(key, active)}</span>
              <span className="activity-tab-bottom__label">{labelFor(key)}</span>
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => setMoreOpen((v) => !v)}
          className={`activity-tab-bottom touch-manipulation ${moreOpen || moreActive ? 'is-active' : ''}`}
          aria-expanded={moreOpen}
        >
          <span className="activity-tab-bottom__icon">
            <MoreIcon />
          </span>
          <span className="activity-tab-bottom__label">{t('monitor.more')}</span>
        </button>
      </nav>
      {moreOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-[90] bg-black/50 md:hidden"
            aria-label={t('common.dismiss')}
            onClick={() => setMoreOpen(false)}
          />
          <div className="fixed bottom-[calc(56px+env(safe-area-inset-bottom))] left-0 right-0 z-[91] mx-3 mb-2 overflow-hidden rounded-2xl border border-[var(--console-line)] bg-[var(--console-sidebar)] shadow-2xl md:hidden">
            <p className="border-b border-[var(--console-line)] px-4 py-2 text-[12px] text-[var(--console-sub)]">
              {t('monitor.more')}
            </p>
            <p className="border-b border-[var(--console-line)] px-4 py-2 text-[12px] leading-relaxed text-[var(--console-faint)]">
              {t('mobileShell.moreNote')}
            </p>
            <div className="grid grid-cols-2 gap-1 p-2">
              {MOBILE_MORE_ACTIVITIES.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    onActivityChange(key);
                    setMoreOpen(false);
                  }}
                  className={`flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-[12px] ${
                    current === key
                      ? 'bg-[var(--console-card)] text-[var(--console-ink)]'
                      : 'text-[var(--console-sub)] hover:bg-[var(--console-card)] hover:text-[var(--console-ink)]'
                  }`}
                >
                  <span className="shrink-0 opacity-80">{deskIcon(key, current === key)}</span>
                  {labelFor(key)}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}

export default function ActivityBar({
  activity,
  activeView,
  monitorTab,
  onActivityChange,
  placement = 'sidebar',
  onMobileTasks,
  onMobileUsage,
  onMobileConsoleTab,
}: ActivityBarProps) {
  const { t } = useTranslation();
  const items: BarItem[] = DESK_ACTIVITIES.map((a) => ({
    key: a.key,
    label: t(`nav.${a.key}`, { defaultValue: a.label }),
    icon: (on) => deskIcon(a.key, on),
  }));

  if (placement === 'bottom') {
    return (
      <MobileBottomBar
        activity={activity}
        activeView={activeView}
        monitorTab={monitorTab}
        onActivityChange={onActivityChange}
        onMobileTasks={onMobileTasks}
        onMobileUsage={onMobileUsage}
        onMobileConsoleTab={onMobileConsoleTab}
      />
    );
  }

  return (
    <nav className="activity-rail hidden md:flex" aria-label="主活動">
      <ActivityButtons
        items={items}
        activity={activity}
        onActivityChange={onActivityChange}
        placement="sidebar"
      />
    </nav>
  );
}
