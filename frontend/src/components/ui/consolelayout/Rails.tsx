/**
 * 三欄欄位容器與欄內導航／滾動區。
 */

import { forwardRef, type ReactNode } from 'react';
import { consoleLayout } from '../../../lib/consoleLayout';
import { cn } from './cn';
import type { DivProps, SectionNavItem } from './types';

export function ConsoleLeftRail({ className, children, ...rest }: DivProps) {
  return (
    <aside className={cn(consoleLayout.colLeft, className)} {...rest}>
      {children}
    </aside>
  );
}

export function ConsoleCenterColumn({ className, children, ...rest }: DivProps) {
  return (
    <main className={cn(consoleLayout.colCenter, className)} {...rest}>
      {children}
    </main>
  );
}

export function ConsoleRightRail({ className, children, ...rest }: DivProps) {
  return (
    <aside className={cn(consoleLayout.colRight, className)} {...rest}>
      {children}
    </aside>
  );
}

/** 欄內可滾動區（4px scrollbar，最後手段） */
export const ConsoleColumnScroll = forwardRef<HTMLDivElement, DivProps>(function ConsoleColumnScroll(
  { className, children, ...rest },
  ref,
) {
  return (
    <div ref={ref} className={cn(consoleLayout.colScroll, consoleLayout.pagePaddingDense, className)} {...rest}>
      {children}
    </div>
  );
});

/** 左欄垂直 section 導航 */
export function ConsoleRailNav({
  sections,
  activeId,
  onSelect,
  header,
  footer,
  className,
}: {
  sections: SectionNavItem[];
  activeId?: string;
  onSelect: (id: string) => void;
  header?: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <nav className={cn(consoleLayout.railNav, className)} aria-label="區塊導航">
      {header}
      {sections.map((s) => {
        const active = activeId === s.id;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            className={cn(consoleLayout.railItem, active && consoleLayout.railItemActive)}
          >
            {s.label}
          </button>
        );
      })}
      {footer}
    </nav>
  );
}

export const PanelScroll = forwardRef<HTMLDivElement, DivProps>(function PanelScroll(
  { className, children, ...rest },
  ref,
) {
  return (
    <div ref={ref} className={cn(consoleLayout.pageScroll, className)} {...rest}>
      {children}
    </div>
  );
});
