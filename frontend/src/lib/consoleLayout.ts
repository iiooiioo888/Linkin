/**
 * 控制台版面節奏（DESIGN.md：canvas #010102、surface #0f1011、hairline、dense rhythm）。
 *
 * 頁面 px-6 py-4 · 區塊 stack gap-4 · 卡片 p-4 · KPI 列 gap-2 · 空狀態 py-12
 */
export const consoleLayout = {
  /** 可滾動頁面根（多數監控分頁） */
  page: 'flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas px-6 py-4 text-[#f7f8f8]',
  /** 不可滾動外殼（內含子面板自管滾動） */
  pageShell: 'flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas',
  /** 內層滾動區（與 page 同節奏） */
  pageScroll: 'min-h-0 flex-1 overflow-y-auto px-6 py-4',
  pagePadding: 'px-6 py-4',
  pagePaddingDense: 'px-4 py-4',
  /** 區塊垂直堆疊 */
  sectionStack: 'space-y-4',
  sectionGap: 'gap-4',
  /** KPI／統計列 */
  kpiGrid: 'grid grid-cols-2 gap-2 lg:grid-cols-4',
  /** 管線／角色工作台指標帶（6 格） */
  kpiStrip6:
    'grid shrink-0 grid-cols-2 gap-2 border-b border-white/[0.06] px-6 py-4 sm:grid-cols-3 lg:grid-cols-6',
  /** rd-shell 控制台外殼（內層 rd-* 骨架保留，僅對齊外緣節奏） */
  rdShell: 'console-rd-shell rd-shell',
  rdToolbar:
    'flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-6 py-4',
  /** 雙欄卡片格 */
  cardGrid: 'grid gap-4 lg:grid-cols-2',
  /** apple-card 外殼（表頭＋內容分離時 !p-0） */
  card: 'apple-card apple-card--tight !p-0 overflow-hidden',
  kpiCard: 'apple-card apple-card--tight !p-0 px-4 py-3',
  cardHeader:
    'border-b border-white/[0.08] bg-[#1C1C1E] px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]',
  cardBody: 'p-4',
  cardBodyDense: 'p-3',
  /** 內嵌小卡（非 apple-card） */
  insetCard: 'rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-4',
  empty: 'py-12 text-center',
  emptySm: 'py-8 text-center',
  maxContent: 'mx-auto w-full max-w-6xl',
  tabBar:
    'flex shrink-0 items-center gap-2 overflow-x-auto border-b border-white/[0.06] px-6 py-3',
  toolbar: 'flex flex-wrap items-center justify-between gap-2',
  title: 'text-sm font-semibold',
  subtitle: 'mt-0.5 text-[11px] text-[#8a8f98]',
  meta: 'mt-1 text-[11px] text-[#636366]',
  errorBar: 'rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300',
  noticeBar: 'rounded-md border border-[#007AFF]/30 bg-[#007AFF]/10 px-3 py-2 text-xs text-[#64D2FF]',
  refreshBtn:
    'rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]',
  kpiLabel: 'text-[10px] uppercase tracking-wider text-[#62666d]',
  kpiValue: 'mt-1 font-mono text-lg text-[#f7f8f8]',
} as const;

export type ConsoleLayoutToken = keyof typeof consoleLayout;
