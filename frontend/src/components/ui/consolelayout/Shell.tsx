/**
 * 版面骨架：PanelShell（頁面外殼）與 ConsoleThreeColumn（三欄主 grid＋行動分頁）。
 */

import { useState } from 'react';
import { useMediaQuery } from '../../../hooks/useMediaQuery';
import { consoleLayout } from '../../../lib/consoleLayout';
import { cn } from './cn';
import type { DivProps } from './types';

type ConsoleMobilePane = 'left' | 'center' | 'right';

export function PanelShell({
  scroll = true,
  constrained,
  className,
  children,
  ...rest
}: DivProps & { scroll?: boolean; constrained?: boolean }) {
  const base = scroll ? consoleLayout.page : consoleLayout.pageShell;
  const inner = constrained ? consoleLayout.maxContent : undefined;
  if (!inner) {
    return (
      <div className={cn(base, className)} {...rest}>
        {children}
      </div>
    );
  }
  return (
    <div className={cn(base, className)} {...rest}>
      <div className={inner}>{children}</div>
    </div>
  );
}

/** OCD 三欄主 grid — 左 216 / 中 1fr / 右 304（≥1440）；<1024 單欄 + 分頁切換 */
export function ConsoleThreeColumn({
  className,
  children,
  mobileLabels,
  liteShell = false,
  ...rest
}: DivProps & {
  mobileLabels?: Partial<Record<ConsoleMobilePane, string>>;
  /** 行動 Lite Shell：預設主視圖欄、<768 亦啟用分欄分頁 */
  liteShell?: boolean;
}) {
  const isWideConsole = useMediaQuery('(min-width: 1024px)', true);
  const isMobileWidth = useMediaQuery('(max-width: 767px)', false);
  const useMobileTabs = !isWideConsole || (liteShell && isMobileWidth);
  const [mobilePane, setMobilePane] = useState<ConsoleMobilePane>(liteShell && isMobileWidth ? 'center' : 'center');

  const labels: Record<ConsoleMobilePane, string> = {
    left: mobileLabels?.left ?? '導覽',
    center: mobileLabels?.center ?? '主視圖',
    right: mobileLabels?.right ?? '詳情',
  };

  return (
    <div
      className={cn(
        consoleLayout.threeColumn,
        useMobileTabs && 'console-three-col--mobile-tabs',
        useMobileTabs && `console-three-col--show-${mobilePane}`,
        className,
      )}
      data-console-layout={useMobileTabs ? 'tabbed' : 'wide'}
      {...rest}
    >
      {useMobileTabs ? (
        <nav className="console-mobile-col-tabs" role="tablist" aria-label="欄位切換">
          {(['left', 'center', 'right'] as ConsoleMobilePane[]).map((pane) => (
            <button
              key={pane}
              type="button"
              role="tab"
              aria-selected={mobilePane === pane}
              className={cn('console-mobile-col-tab', mobilePane === pane && 'on')}
              onClick={() => setMobilePane(pane)}
            >
              {labels[pane]}
            </button>
          ))}
        </nav>
      ) : null}
      {children}
    </div>
  );
}
