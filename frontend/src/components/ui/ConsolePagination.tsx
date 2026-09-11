/**
 * 控制台換頁器 — 無滾動條，以分頁切換內容。
 */
import { cn } from './ConsoleLayout';

const btnCls =
  'rounded-full px-3 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40';

export function ConsolePagination({
  page,
  totalPages,
  onPageChange,
  className,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  if (totalPages <= 1) return null;

  return (
    <nav
      className={cn(
        'flex shrink-0 items-center justify-center gap-3 border-t border-white/[0.06] px-4 py-2.5',
        className,
      )}
      aria-label="分頁"
    >
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className={cn(btnCls, 'border border-[var(--console-line)] bg-[var(--console-card)] text-[var(--console-sub)] hover:text-[var(--console-ink)]')}
      >
        上一頁
      </button>
      <span className="min-w-[4.5rem] text-center text-[11px] tabular-nums text-[var(--console-sub)]">
        第 {page} 頁
        <span className="text-[var(--console-faint)]"> / {totalPages}</span>
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className={cn(btnCls, 'border border-[var(--console-blue)]/30 bg-[var(--console-blue)]/10 text-[var(--console-blue)] hover:bg-[var(--console-blue)]/20')}
      >
        下一頁
      </button>
    </nav>
  );
}

/** 分頁內容外殼：上方內容 + 底部分頁器 */
export function ConsolePageFrame({
  page,
  totalPages,
  onPageChange,
  children,
  className,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex h-full min-h-0 flex-1 flex-col overflow-hidden', className)}>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      <ConsolePagination page={page} totalPages={totalPages} onPageChange={onPageChange} />
    </div>
  );
}
