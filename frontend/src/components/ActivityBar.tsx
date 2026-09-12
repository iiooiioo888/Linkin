/**
 * ActivityBar — 對話 / 控制台 / 已註冊世界模組 / 實驗室。
 * 桌面：左側垂直欄；行動端：底部 Tab 列（Chat / Tasks / Wallet + 更多）。
 */
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { ActivityKey } from '../lib/monitorTabs';
import type { MonitorTab, ViewKey } from './AppShell';
import { useWorldModules, type ModuleIconKey } from '../lib/worldModules';

interface ActivityBarProps {
  activity: ActivityKey;
  activeView?: ViewKey;
  monitorTab?: MonitorTab;
  onActivityChange: (activity: ActivityKey) => void;
  /** 桌面左欄 vs 行動底欄 */
  placement?: 'sidebar' | 'bottom';
  onMobileTasks?: () => void;
  onMobileWallet?: () => void;
}

function ChatIcon({ active }: { active: boolean }) {
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

function TasksIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="3" y="3" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="10" y="3" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="3" y="10" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <path d="M11 12h4M11 14.5h3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function WalletIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M3 5.5h12a1 1 0 011 1v6a1 1 0 01-1 1H3a1 1 0 01-1-1v-6a1 1 0 011-1z"
        stroke="currentColor"
        strokeWidth="1.3"
      />
      <circle cx="13" cy="9" r="1.2" fill="currentColor" />
      <path d="M3 7.5V4.5a1 1 0 011-1h9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
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

function ConsoleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="2" y="3" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.3" />
      <path d="M6 15h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function LabIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <path
        d="M6 2.5h6M7.5 2.5v4.2L3.8 14.2A1.4 1.4 0 005 16h8a1.4 1.4 0 001.2-1.8L10.5 6.7V2.5"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <path d="M7.2 10.5h3.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

function MinecraftIcon() {
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

function GenericModuleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
      <rect x="3" y="3" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="10" y="3" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="3" y="10" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
      <rect x="10" y="10" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  );
}

function moduleIcon(icon: ModuleIconKey): ReactNode {
  if (icon === 'minecraft') return <MinecraftIcon />;
  return <GenericModuleIcon />;
}

type BarItem = { key: ActivityKey; label: string; icon: (active: boolean) => ReactNode };

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

  return (
    <>
      {items.map((item) => {
        const active = activity === item.key;
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onActivityChange(item.key)}
            className={
              isBottom
                ? `activity-tab-bottom touch-manipulation ${active ? 'is-active' : ''}`
                : `mb-0.5 flex h-9 w-9 touch-manipulation items-center justify-center rounded-lg transition-colors ${
                    active
                      ? 'bg-white/[0.08] text-[#F5F5F7]'
                      : 'text-[#636366] hover:bg-white/[0.04] hover:text-[#AEAEB2]'
                  }`
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
  activeView = 'chat',
  monitorTab = 'live',
  onActivityChange,
  onMobileTasks,
  onMobileWallet,
  overflowItems,
}: {
  activity: ActivityKey;
  activeView?: ViewKey;
  monitorTab?: MonitorTab;
  onActivityChange: (activity: ActivityKey) => void;
  onMobileTasks?: () => void;
  onMobileWallet?: () => void;
  overflowItems: BarItem[];
}) {
  const { t } = useTranslation();
  const [moreOpen, setMoreOpen] = useState(false);
  const onMonitor = activeView === 'monitor' || activeView === 'traces' || activeView === 'task' || activeView === 'raho';
  const tasksActive =
    onMonitor && (monitorTab === 'tasks' || monitorTab === 'pipeline' || activeView === 'traces');
  const walletActive =
    onMonitor && (monitorTab === 'credits' || monitorTab === 'billing' || monitorTab === 'models');

  return (
    <>
      <nav className="activity-bar-bottom md:hidden" aria-label="主活動">
        <button
          type="button"
          onClick={() => onActivityChange('chat')}
          className={`activity-tab-bottom touch-manipulation ${activity === 'chat' ? 'is-active' : ''}`}
          aria-current={activity === 'chat' ? 'page' : undefined}
        >
          <span className="activity-tab-bottom__icon"><ChatIcon active={activity === 'chat'} /></span>
          <span className="activity-tab-bottom__label">{t('nav.chat')}</span>
        </button>
        <button
          type="button"
          onClick={() => onMobileTasks?.()}
          className={`activity-tab-bottom touch-manipulation ${tasksActive ? 'is-active' : ''}`}
        >
          <span className="activity-tab-bottom__icon"><TasksIcon /></span>
          <span className="activity-tab-bottom__label">{t('nav.tasks')}</span>
        </button>
        <button
          type="button"
          onClick={() => onMobileWallet?.()}
          className={`activity-tab-bottom touch-manipulation ${walletActive ? 'is-active' : ''}`}
        >
          <span className="activity-tab-bottom__icon"><WalletIcon /></span>
          <span className="activity-tab-bottom__label">{t('nav.wallet')}</span>
        </button>
        <button
          type="button"
          onClick={() => setMoreOpen((v) => !v)}
          className={`activity-tab-bottom touch-manipulation ${moreOpen ? 'is-active' : ''}`}
          aria-expanded={moreOpen}
        >
          <span className="activity-tab-bottom__icon"><MoreIcon /></span>
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
          <div className="fixed bottom-[calc(56px+env(safe-area-inset-bottom))] left-0 right-0 z-[91] mx-3 mb-2 overflow-hidden rounded-2xl border border-white/[0.08] bg-[var(--console-sidebar)] shadow-2xl md:hidden">
            <p className="border-b border-white/[0.06] px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
              {t('monitor.more')}
            </p>
            <p className="border-b border-white/[0.06] px-4 py-2 text-[10px] leading-relaxed text-[var(--console-sub)]">
              {t('mobileShell.moreNote')}
            </p>
            <div className="grid grid-cols-2 gap-1 p-2">
              {overflowItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => {
                    onActivityChange(item.key);
                    setMoreOpen(false);
                  }}
                  className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-[12px] text-[var(--console-sub)] hover:bg-white/[0.04] hover:text-[var(--console-ink)]"
                >
                  <span className="shrink-0 opacity-80">{item.icon(activity === item.key)}</span>
                  {item.label}
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
  onMobileWallet,
}: ActivityBarProps) {
  const { t } = useTranslation();
  const modules = useWorldModules();
  const items: BarItem[] = [
    { key: 'chat', label: t('nav.chat'), icon: (on) => <ChatIcon active={on} /> },
    { key: 'console', label: t('nav.console'), icon: () => <ConsoleIcon /> },
    ...modules.map((spec) => ({
      key: spec.id,
      label: spec.id === 'minecraft' ? t('nav.minecraft') : spec.title,
      icon: () => moduleIcon(spec.icon),
    })),
    { key: 'lab', label: t('nav.lab'), icon: () => <LabIcon /> },
  ];

  if (placement === 'bottom') {
    const overflowItems = items.filter((i) => i.key !== 'chat');
    return (
      <MobileBottomBar
        activity={activity}
        activeView={activeView}
        monitorTab={monitorTab}
        onActivityChange={onActivityChange}
        onMobileTasks={onMobileTasks}
        onMobileWallet={onMobileWallet}
        overflowItems={overflowItems}
      />
    );
  }

  return (
    <nav
      className="hidden w-11 shrink-0 flex-col items-center border-r border-white/[0.06] apple-chrome py-2 md:flex"
      aria-label="主活動"
    >
      <ActivityButtons
        items={items}
        activity={activity}
        onActivityChange={onActivityChange}
        placement="sidebar"
      />
    </nav>
  );
}
