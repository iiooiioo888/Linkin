/**
 * KPI 卡片／網格、巨型 KPI、方案 chip 與稠密摘要卡。
 */

import type { ReactNode } from 'react';
import { consoleLayout } from '../../../lib/consoleLayout';
import { cn } from './cn';
import type { DivProps } from './types';

/** 巨型 KPI（64–72px；每頁 ≤3；accent 僅一處） */
export function ConsoleGiantKpi({
  label,
  value,
  unit,
  meta,
  accent,
  spark,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  meta?: ReactNode;
  accent?: boolean;
  spark?: number[];
  className?: string;
}) {
  const bars = spark ?? [];
  const max = bars.length ? Math.max(...bars, 1) : 1;
  return (
    <div className={cn('console-giant-kpi', className)}>
      <div>
        <p className="console-giant-kpi__label">{label}</p>
        <p className={cn('console-giant-kpi__value', accent && 'accent')}>
          {value}
          {unit ? <span className="unit">{unit}</span> : null}
        </p>
        {meta ? <p className="console-giant-kpi__meta">{meta}</p> : null}
      </div>
      {bars.length > 0 ? (
        <div className="console-giant-kpi__spark" aria-hidden>
          {bars.map((v, i) => (
            <span
              key={i}
              className={cn(
                (accent && i === bars.length - 1 && 'accent') ||
                  (v >= max * 0.85 && !accent && 'on'),
              )}
              style={{ height: `${Math.max(12, (v / max) * 100)}%` }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ConsolePlanChip({
  label,
  active,
  onClick,
  hint,
}: {
  label: ReactNode;
  active?: boolean;
  onClick?: () => void;
  hint?: ReactNode;
}) {
  const Tag = onClick ? 'button' : 'span';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cn(consoleLayout.chip, active && consoleLayout.chipActive)}
      title={typeof hint === 'string' ? hint : undefined}
    >
      {label}
    </Tag>
  );
}

export function ConsoleSnippetList({
  title,
  children,
  className,
}: {
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('console-dense-card', className)}>
      {title ? <p className="console-dense-card__head">{title}</p> : null}
      <div className="console-dense-card__body !py-2">{children}</div>
    </div>
  );
}

export function KpiGrid({ fill, className, children, ...rest }: DivProps & { fill?: boolean }) {
  return (
    <div className={cn(fill ? consoleLayout.kpiGridFill : consoleLayout.kpiGrid, className)} {...rest}>
      {children}
    </div>
  );
}

export function KpiGrid4({ fill, className, children, ...rest }: DivProps & { fill?: boolean }) {
  return (
    <div className={cn(fill ? consoleLayout.kpiGrid4Fill : consoleLayout.kpiGrid4, className)} {...rest}>
      {children}
    </div>
  );
}

export function KpiGrid6({ fill, className, children, ...rest }: DivProps & { fill?: boolean }) {
  return (
    <div className={cn(fill ? consoleLayout.kpiGrid6Fill : consoleLayout.kpiGrid6, className)} {...rest}>
      {children}
    </div>
  );
}

export function WarnBar({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn(consoleLayout.warnBar, className)}>{children}</div>;
}

export function KpiCard({
  label,
  value,
  hint,
  accent,
  valueClassName,
  className,
  spark,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  accent?: boolean;
  valueClassName?: string;
  className?: string;
  spark?: number[];
}) {
  const bars = spark ?? [];
  const max = bars.length ? Math.max(...bars, 1) : 1;
  return (
    <div className={cn(consoleLayout.kpiCard, 'flex min-h-0 flex-col justify-between', className)}>
      <div>
        <p className={consoleLayout.kpiLabel}>{label}</p>
        <p className={cn(accent ? consoleLayout.kpiValueAccent : consoleLayout.kpiValue, valueClassName)}>{value}</p>
        {hint ? <p className="mt-1 text-[10px] text-[var(--console-sub)]">{hint}</p> : null}
      </div>
      {bars.length > 0 ? (
        <div className="console-giant-kpi__spark !mt-2 !h-4" aria-hidden>
          {bars.map((v, i) => (
            <span
              key={i}
              className={cn(v >= max * 0.85 && 'on')}
              style={{ height: `${Math.max(20, (v / max) * 100)}%` }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
