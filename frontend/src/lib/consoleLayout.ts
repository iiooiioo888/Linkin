/**
 * 控制台版面節奏 — OCD 三欄 dense 設計（8pt grid、~100vh 單頁）。
 *
 * 桌面 ≥1440：左 224px · 中 1fr · 右 280px
 */
export const consoleLayout = {
  /** 可滾動頁面根（多數監控分頁） */
  page:
    'flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden console-canvas px-4 py-4 text-[var(--console-ink)] sm:px-6',
  /** 不可滾動外殼（內含子面板自管滾動） */
  pageShell: 'flex h-full min-h-0 flex-1 flex-col overflow-hidden console-canvas',
  /** Tab 內可伸縮內容區（SectionHeader 下方） */
  pageContent: 'flex min-h-0 flex-1 flex-col overflow-hidden',
  /** 內層滾動區（與 page 同節奏） */
  pageScroll: 'min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 sm:px-6 console-col-scroll',
  pagePadding: 'px-4 py-4 sm:px-6',
  pagePaddingDense: 'px-3 py-3 sm:px-4',
  /** 三欄主 grid */
  threeColumn: 'console-three-col',
  colLeft: 'console-col-left',
  colCenter: 'console-col-center',
  colRight: 'console-col-right',
  colScroll: 'console-col-scroll',
  /** 區塊垂直堆疊 */
  sectionStack: 'flex min-h-0 flex-col gap-2',
  sectionGap: 'gap-2',
  /** KPI／統計列（3 欄） */
  kpiGrid: 'console-dense-grid console-dense-grid--3 console-dense-grid--equal-rows',
  /** KPI／統計列（4 欄 — 系統總覽） */
  kpiGrid4: 'console-dense-grid console-dense-grid--4 console-dense-grid--equal-rows',
  /** KPI 格填滿可用高度（分頁內無滾動） */
  kpiGridFill:
    'console-dense-grid console-dense-grid--3 console-dense-grid--equal-rows min-h-0 flex-1 [&>*]:min-h-0',
  kpiGrid4Fill:
    'console-dense-grid console-dense-grid--4 console-dense-grid--equal-rows min-h-0 flex-1 [&>*]:min-h-0',
  /** 巨型 KPI 列（≤3 個） */
  giantKpiRow: 'console-kpi-row shrink-0',
  /** 管線／角色工作台指標帶 */
  kpiStrip6:
    'grid shrink-0 grid-cols-2 gap-2 overflow-x-auto border-b border-[var(--console-line)] px-4 py-3 sm:grid-cols-3 sm:px-4 lg:grid-cols-6',
  /** rd-shell 控制台外殼 */
  rdShell: 'console-rd-shell rd-shell',
  rdToolbar:
    'flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-[var(--console-line)] px-4 py-3 sm:px-4',
  /** 雙欄卡片格 */
  cardGrid: 'console-dense-grid console-dense-grid--2',
  /** 雙欄卡片格填滿可用高度 */
  cardGridFill:
    'console-dense-grid console-dense-grid--2 min-h-0 flex-1 [&>*]:flex [&>*]:min-h-0 [&>*]:flex-col',
  /** dense card 外殼 */
  card: 'console-dense-card overflow-hidden',
  kpiCard: 'console-dense-card !p-0 px-3 py-2',
  cardHeader: 'console-dense-card__head',
  cardBody: 'console-dense-card__body',
  cardBodyDense: 'console-dense-card__body !p-2',
  /** 內嵌小卡 */
  insetCard: 'rounded-lg border border-[var(--console-line)] bg-[var(--console-card-elevated)] p-3',
  empty: 'py-8 text-center text-[var(--console-sub)]',
  emptySm: 'py-6 text-center text-[var(--console-sub)]',
  maxContent: 'mx-auto w-full max-w-6xl',
  tabBar:
    'flex shrink-0 items-center gap-2 overflow-x-auto border-b border-[var(--console-line)] px-4 py-3 sm:px-4',
  /** 區塊分頁導航（水平 pill；嵌入子面板時使用） */
  sectionNav:
    'sticky top-0 z-20 flex shrink-0 items-center gap-2 overflow-x-auto border-b border-[var(--console-line)] bg-[var(--console-bg)]/92 px-4 py-2 backdrop-blur-md sm:px-4',
  /** 左欄垂直導航 */
  railNav: 'console-rail-nav',
  railItem: 'console-rail-item',
  railItemActive: 'on',
  /** 區塊 anchor 偏移 */
  sectionAnchor: 'scroll-mt-14',
  sectionGapLg: 'space-y-4',
  toolbar: 'flex flex-wrap items-center justify-between gap-2',
  title: 'text-[13px] font-semibold text-[var(--console-ink)]',
  subtitle: 'mt-0.5 text-[11px] text-[var(--console-sub)]',
  meta: 'mt-1 text-[10px] text-[var(--console-faint)]',
  errorBar:
    'rounded-md border border-[var(--console-danger)]/30 bg-[var(--console-danger)]/10 px-3 py-2 text-xs text-[var(--console-danger)]',
  noticeBar:
    'rounded-md border border-[var(--console-blue)]/30 bg-[var(--console-blue)]/10 px-3 py-2 text-xs text-[var(--console-blue)]',
  refreshBtn:
    'rounded-lg border border-[var(--console-line)] bg-[var(--console-card)] px-2 py-1 text-[11px] text-[var(--console-sub)] hover:text-[var(--console-ink)]',
  kpiLabel: 'text-[10px] uppercase tracking-wider text-[var(--console-faint)]',
  kpiValue: 'mt-1 font-mono text-2xl tabular-nums text-[var(--console-ink)]',
  kpiValueAccent: 'mt-1 font-mono text-2xl tabular-nums text-[var(--console-accent)]',
  chip: 'console-chip',
  chipActive: 'on',
  snippetRow: 'console-snippet-row',
} as const;

export type ConsoleLayoutToken = keyof typeof consoleLayout;
