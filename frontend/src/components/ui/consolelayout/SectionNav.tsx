/**
 * 區塊分頁導航與 rd 工具列。
 */

import type { ReactNode } from 'react';
import { consoleLayout } from '../../../lib/consoleLayout';
import { cn } from './cn';
import type { SectionNavItem } from './types';

/** 區塊分頁導航（pill bar；切換可見區塊，不觸發頁面滾動） */
export function ConsoleSectionNav({
  sections,
  activeId,
  onSelect,
  className,
}: {
  sections: SectionNavItem[];
  activeId?: string;
  onSelect: (id: string) => void;
  className?: string;
}) {
  return (
    <nav className={cn(consoleLayout.sectionNav, className)} aria-label="區塊導航">
      {sections.map((s) => {
        const active = activeId === s.id;
        return (
          <button
            key={s.id}
            type="button"
            onClick={() => onSelect(s.id)}
            className={cn(
              'shrink-0 rounded-full px-3 py-1.5 text-[12px] font-medium transition-colors',
              active
                ? 'border border-[var(--console-line-strong)] bg-[var(--console-card)] text-[var(--console-ink)]'
                : 'border border-transparent bg-[var(--console-card)]/40 text-[var(--console-sub)] hover:text-[var(--console-ink)]',
            )}
          >
            {s.label}
          </button>
        );
      })}
    </nav>
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
          <h2 className={cn(consoleLayout.title, 'm-0 text-[var(--console-sub)]')}>{title}</h2>
          {actions}
        </>
      )}
    </div>
  );
}
