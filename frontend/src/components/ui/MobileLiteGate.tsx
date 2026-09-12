/**
 * Mobile Lite Shell 共用閘門 — 行動端預設摘要 + 桌面提示，可選展開完整面板。
 */
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useIsMobileLiteShell } from '../../hooks/useMediaQuery';

export function MobileLiteBanner({
  onExpand,
  className = '',
}: {
  onExpand?: () => void;
  className?: string;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={`mobile-lite-banner rounded-xl border border-[color-mix(in_srgb,var(--console-accent)_25%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_8%,transparent)] px-3 py-2.5 ${className}`}
      data-testid="mobile-lite-banner"
    >
      <p className="text-[11px] leading-relaxed text-[var(--console-sub)]">{t('mobileShell.desktopHint')}</p>
      {onExpand ? (
        <button
          type="button"
          onClick={onExpand}
          className="mt-2 text-[11px] font-medium text-[var(--console-accent)] hover:underline"
        >
          {t('mobileShell.showFullPanel')}
        </button>
      ) : null}
    </div>
  );
}

export function MobileLiteGate({
  children,
  summary,
  defaultExpanded = false,
  gated = true,
}: {
  children: ReactNode;
  /** 行動 Lite 模式下、未展開時顯示的摘要（可選） */
  summary?: ReactNode;
  defaultExpanded?: boolean;
  /** false 時即使在行動也直接渲染 children */
  gated?: boolean;
}) {
  const lite = useIsMobileLiteShell();
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (!lite || !gated || expanded) {
    return <>{children}</>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
      <MobileLiteBanner onExpand={() => setExpanded(true)} />
      {summary}
    </div>
  );
}
