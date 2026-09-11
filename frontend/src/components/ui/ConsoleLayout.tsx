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

/** OCD 三欄主 grid — 左 216 / 中 1fr / 右 304（≥1440） */
export function ConsoleThreeColumn({ className, children, ...rest }: DivProps) {
  return (
    <div className={cn(consoleLayout.threeColumn, className)} {...rest}>
      {children}
    </div>
  );
}

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
          <h2 className={cn(consoleLayout.title, 'm-0 text-[var(--console-sub)]')}>{title}</h2>
          {actions}
        </>
      )}
    </div>
  );
}

export { consoleLayout };
