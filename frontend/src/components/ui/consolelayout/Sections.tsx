/**
 * 內容區容器、SectionHeader 與單頁區塊外殼。
 */

import type { ReactNode } from 'react';
import { consoleLayout } from '../../../lib/consoleLayout';
import { cn } from './cn';
import type { DivProps } from './types';

/** 分頁 tab 內容區 — 禁止整頁／卡片滾動，溢出由子層換頁處理 */
export function ConsoleTabBody({ className, children, ...rest }: DivProps) {
  return (
    <div
      className={cn('flex min-h-0 flex-1 flex-col overflow-hidden', consoleLayout.pagePadding, className)}
      {...rest}
    >
      {children}
    </div>
  );
}

/** SectionHeader 下方可伸縮內容槽（與 ConsolePageFrame 分頁器搭配） */
export function ConsoleTabContent({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.pageContent, className)} {...rest}>
      {children}
    </div>
  );
}

export function PanelSection({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.sectionStack, className)} {...rest}>
      {children}
    </div>
  );
}

export function SectionHeader({
  title,
  description,
  meta,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn(consoleLayout.toolbar, className)}>
      <div>
        <h2 className={consoleLayout.title}>{title}</h2>
        {description ? <p className={consoleLayout.subtitle}>{description}</p> : null}
        {meta ? <p className={consoleLayout.meta}>{meta}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function PanelAlert({
  tone = 'error',
  className,
  children,
  ...rest
}: DivProps & { tone?: 'error' | 'notice' }) {
  const toneCls = tone === 'notice' ? consoleLayout.noticeBar : consoleLayout.errorBar;
  return (
    <div className={cn(toneCls, className)} {...rest}>
      {children}
    </div>
  );
}

export function PanelTabBar({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.tabBar, className)} {...rest}>
      {children}
    </div>
  );
}

/** 單頁區塊外殼（anchor + 標題 + 內容堆疊） */
export function ConsoleSection({
  id,
  title,
  description,
  actions,
  children,
  className,
  fill,
}: {
  id: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /** 垂直填滿父層（分頁 frame 內使用） */
  fill?: boolean;
}) {
  return (
    <section
      id={id}
      className={cn(
        consoleLayout.sectionAnchor,
        fill ? 'flex min-h-0 flex-1 flex-col gap-3 overflow-hidden' : consoleLayout.sectionStack,
        className,
      )}
    >
      <SectionHeader
        title={title}
        description={description}
        actions={actions}
        className={fill ? 'shrink-0' : undefined}
      />
      {fill ? (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      ) : (
        children
      )}
    </section>
  );
}
