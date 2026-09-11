/**
 * 控制台共用版面元件 — 包裝 consoleLayout tokens，避免各面板重複 ad-hoc padding。
 */
import {
  forwardRef,
  useCallback,
  useEffect,
  useState,
  type HTMLAttributes,
  type ReactNode,
  type RefObject,
} from 'react';
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

export function KpiGrid({ fill, className, children, ...rest }: DivProps & { fill?: boolean }) {
  return (
    <div className={cn(fill ? consoleLayout.kpiGridFill : consoleLayout.kpiGrid, className)} {...rest}>
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

export type SectionNavItem = { id: string; label: string };

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
              'shrink-0 rounded-full px-3.5 py-1.5 text-[12px] font-medium transition-colors',
              active
                ? 'bg-[#007AFF] text-white'
                : 'bg-white/[0.04] text-[#AEAEB2] hover:text-[#F5F5F7]',
            )}
          >
            {s.label}
          </button>
        );
      })}
    </nav>
  );
}

/** IntersectionObserver scroll spy for single-page section nav */
export function useSectionScrollSpy(
  sectionIds: string[],
  scrollRootRef: RefObject<HTMLElement | null>,
): string | undefined {
  const [active, setActive] = useState<string | undefined>(sectionIds[0]);

  useEffect(() => {
    const root = scrollRootRef.current;
    if (!root || sectionIds.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const id = visible[0]?.target.id;
        if (id) setActive(id);
      },
      { root, rootMargin: '-12% 0px -55% 0px', threshold: [0, 0.15, 0.4, 0.65] },
    );

    for (const id of sectionIds) {
      const el = root.querySelector(`#${CSS.escape(id)}`);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sectionIds, scrollRootRef]);

  return active;
}

export function useScrollToSection(scrollRootRef: RefObject<HTMLElement | null>) {
  return useCallback(
    (id: string) => {
      const root = scrollRootRef.current;
      const el =
        root?.querySelector(`#${CSS.escape(id)}`) ??
        document.getElementById(id);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [scrollRootRef],
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
