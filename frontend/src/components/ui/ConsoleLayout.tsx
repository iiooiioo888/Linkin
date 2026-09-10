/**
 * 控制台共用版面元件 — 包裝 consoleLayout tokens，避免各面板重複 ad-hoc padding。
 */
import type { HTMLAttributes, ReactNode } from 'react';
import { consoleLayout } from '../../lib/consoleLayout';

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

type DivProps = HTMLAttributes<HTMLDivElement>;

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

export function PanelScroll({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.pageScroll, className)} {...rest}>
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

export function KpiGrid({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.kpiGrid, className)} {...rest}>
      {children}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  hint,
  valueClassName,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  valueClassName?: string;
  className?: string;
}) {
  return (
    <div className={cn(consoleLayout.kpiCard, className)}>
      <p className={consoleLayout.kpiLabel}>{label}</p>
      <p className={cn(consoleLayout.kpiValue, valueClassName)}>{value}</p>
      {hint ? <p className="text-[9px] text-[#62666d]">{hint}</p> : null}
    </div>
  );
}

export function ConsoleCard({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.card, className)} {...rest}>
      {children}
    </div>
  );
}

export function ConsoleCardHeader({ className, children, ...rest }: DivProps) {
  return (
    <p className={cn(consoleLayout.cardHeader, className)} {...rest}>
      {children}
    </p>
  );
}

export function ConsoleCardBody({
  dense,
  className,
  children,
  ...rest
}: DivProps & { dense?: boolean }) {
  return (
    <div
      className={cn(dense ? consoleLayout.cardBodyDense : consoleLayout.cardBody, className)}
      {...rest}
    >
      {children}
    </div>
  );
}

export function ConsoleEmpty({
  className,
  children,
  compact,
  ...rest
}: DivProps & { compact?: boolean }) {
  return (
    <div className={cn(compact ? consoleLayout.emptySm : consoleLayout.empty, className)} {...rest}>
      {children}
    </div>
  );
}

/** 控制台內的 rd-shell 外殼（角色／管線／任務共用骨架，外緣 padding 對齊 pagePadding） */
export function ConsoleRdShell({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.rdShell, className)} {...rest}>
      {children}
    </div>
  );
}

export function ConsoleRdToolbar({
  title,
  actions,
  className,
  children,
}: {
  title?: ReactNode;
  actions?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <div className={cn(consoleLayout.rdToolbar, className)}>
      {children ?? (
        <>
          <h2 className={cn(consoleLayout.title, 'm-0 text-[#8a8f98]')}>{title}</h2>
          {actions}
        </>
      )}
    </div>
  );
}

export { consoleLayout };
