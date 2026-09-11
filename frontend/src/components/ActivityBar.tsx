/**
 * ActivityBar — 對話 / 控制台 / 已註冊世界模組 / 實驗室。
 * 桌面：左側垂直欄；行動端：底部 Tab 列（觸控友善）。
 */
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { ActivityKey } from '../lib/monitorTabs';
import { useWorldModules, type ModuleIconKey } from '../lib/worldModules';

interface ActivityBarProps {
  activity: ActivityKey;
  onActivityChange: (activity: ActivityKey) => void;
  /** 桌面左欄 vs 行動底欄 */
  placement?: 'sidebar' | 'bottom';
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

export default function ActivityBar({
  activity,
  onActivityChange,
  placement = 'sidebar',
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
    return (
      <nav className="activity-bar-bottom md:hidden" aria-label="主活動">
        <ActivityButtons
          items={items}
          activity={activity}
          onActivityChange={onActivityChange}
          placement="bottom"
        />
      </nav>
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
