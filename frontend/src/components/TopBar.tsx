/**
 * TopBar — 極簡頂欄。
 */
import { useTranslation } from 'react-i18next';
import { setLocale } from '../i18n';
import { getGateUser, logoutGate } from '../lib/auth';
import { activityTitle, consoleChromeLabel, consoleChromeTabKey, CONSOLE_CHROME_TABS, isCoreActivity, resolveActivity } from '../lib/monitorTabs';
import { labSubTabLabel, type LabSubTab } from '../lib/labTabs';
import type { MonitorTab, ViewKey } from './AppShell';
import WalletBadge from './WalletBadge';

interface TopBarProps {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  labSubTab: LabSubTab;
  traceTaskId: string | null;
  llmConfigured: boolean | null;
  rightPanelOpen: boolean;
  onRightPanelToggle: () => void;
  onOpenSettings: () => void;
  onToggleSidebar: () => void;
  onMonitorTabChange?: (tab: MonitorTab) => void;
  onViewChange?: (view: ViewKey) => void;
}

export default function TopBar({
  activeView,
  monitorTab,
  labSubTab,
  traceTaskId,
  llmConfigured,
  rightPanelOpen,
  onRightPanelToggle,
  onOpenSettings,
  onToggleSidebar,
  onMonitorTabChange,
}: TopBarProps) {
  const { t, i18n } = useTranslation();
  const activity = resolveActivity(activeView, monitorTab);
  const path = consoleChromeLabel(activeView, monitorTab, labSubTabLabel(labSubTab), traceTaskId);
  const chromeKey = activity === 'console' ? consoleChromeTabKey(activeView === 'traces' ? 'traces' : monitorTab) : null;
  const viewLabel =
    activity === 'chat'
      ? t('nav.chat')
      : activity === 'company'
        ? t('nav.company')
      : activity === 'lab'
        ? `${t('nav.lab')} · ${labSubTabLabel(labSubTab)}`
        : !isCoreActivity(activity)
          ? `${activityTitle(activity)} · ${path}`
          : t('nav.console');

  return (
    <header className="app-topbar flex shrink-0 items-center gap-2 border-b apple-chrome px-4">
      <div className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
        {activeView !== 'company' ? (
        <button
          onClick={onToggleSidebar}
          className="apple-icon-btn shrink-0 md:hidden"
          aria-label="切換側邊欄"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path d="M2.5 4h11M2.5 8h11M2.5 12h11" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
        </button>
        ) : null}

        <span
          className={`brand-mark shrink-0 text-[13px] text-[var(--console-ink)] sm:text-[15px] ${
            activity === 'console' ? 'hidden min-[420px]:inline-flex' : ''
          }`}
        >
          <span className="console-status-accent">靈境</span>
          <span className="brand-mark__dot">·</span>
          <span className="hidden min-[400px]:inline">Linkin</span>
        </span>
        {activity === 'console' && onMonitorTabChange ? (
          <>
            <div className="console-hdr-tabs-wrap min-w-0 flex-1">
              <nav className="console-hdr-tabs" aria-label="控制台主入口">
                {CONSOLE_CHROME_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => onMonitorTabChange(tab.key)}
                    className={`console-hdr-tab shrink-0 ${chromeKey === tab.key ? 'on' : ''}`}
                  >
                    {tab.label}
                  </button>
                ))}
              </nav>
            </div>
            {path && chromeKey && chromeKey !== monitorTab ? (
              <span className="hidden min-w-0 truncate text-[11px] text-[var(--console-faint)] lg:inline">· {path}</span>
            ) : null}
          </>
        ) : (
          <>
            <span className="min-w-0 truncate text-[12px] text-[var(--console-faint)]">· {viewLabel}</span>
          </>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-0.5">
        <span className={activity === 'console' ? 'hidden min-[480px]:inline' : 'md:hidden'}>
          <WalletBadge minimal onOpenBilling={() => onMonitorTabChange?.('models')} />
        </span>
        <span className="hidden md:inline-flex">
          <WalletBadge onOpenBilling={() => onMonitorTabChange?.('models')} />
        </span>

        {llmConfigured === false && (
          <button
            type="button"
            onClick={onOpenSettings}
            className="mr-1 hidden items-center gap-1.5 text-[10px] console-status-amber md:flex"
            title="開啟 API 設定"
          >
            <span className="apple-dot apple-dot--warn" />
            未配置
          </button>
        )}

        {getGateUser() ? (
          <span className="hidden max-w-[88px] truncate px-1 text-[10px] text-[var(--console-faint)] md:inline" title={getGateUser() ?? ''}>
            {getGateUser()}
          </span>
        ) : null}

        <button
          type="button"
          onClick={() => void logoutGate()}
          className="apple-icon-btn text-[10px] font-semibold"
          title={t('gate.signOut')}
          aria-label={t('gate.signOut')}
        >
          <span className="topbar-signout-text">{t('gate.signOut')}</span>
          <svg className="topbar-signout-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
            <path d="M6 2.5H3.5a1 1 0 00-1 1V12.5a1 1 0 001 1H6M10.5 11.5L13.5 8.5M13.5 8.5L10.5 5.5M13.5 8.5H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        <button
          type="button"
          onClick={() => setLocale(i18n.language === 'en' ? 'zh-TW' : 'en')}
          className="apple-icon-btn hidden text-[10px] font-semibold md:inline-flex"
          title="Language"
        >
          {i18n.language === 'en' ? 'EN' : '繁'}
        </button>

        {rightPanelOpen && (
          <button
            onClick={onRightPanelToggle}
            className="apple-icon-btn apple-icon-btn--active hidden text-[10px] font-medium md:inline-flex"
            title="關閉 OPC"
          >
            OPC
          </button>
        )}

        <button
          onClick={onOpenSettings}
          className={`apple-icon-btn shrink-0 ${activity === 'console' ? 'hidden min-[480px]:inline-flex' : ''}`}
          title="設定"
          aria-label="設定"
        >
          <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden>
            <path
              d="M7.5 9.5a2 2 0 100-4 2 2 0 000 4z"
              stroke="currentColor"
              strokeWidth="1.2"
            />
            <path
              d="M7.5 1.5l1 .6 1.1-.2.6 1 .9.7 1.1.2v1.2l-.7.9.2 1.1-1 .6-.2 1.1-1.2.2-.6 1-1.1-.2-.9.7-1.1.2v-1.2l.7-.9-.2-1.1 1-.6.2-1.1 1.2-.2.6-1z"
              stroke="currentColor"
              strokeWidth="1"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </header>
  );
}
