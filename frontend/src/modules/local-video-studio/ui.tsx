/** 共用狀態 badge／導覽（MVP UI，無花俏動畫）。 */

const STATUS_CLASS: Record<string, string> = {
  draft: 'bg-zinc-700 text-zinc-200',
  scripting: 'bg-zinc-700 text-zinc-200',
  keyframe_ready: 'bg-sky-900/80 text-sky-200',
  draft_ready: 'bg-amber-900/80 text-amber-100',
  refine_ready: 'bg-violet-900/80 text-violet-100',
  approved: 'bg-emerald-900/80 text-emerald-100',
  rejected: 'bg-red-900/80 text-red-100',
  queued: 'bg-zinc-700 text-zinc-200',
  running: 'bg-sky-900/80 text-sky-200',
  succeeded: 'bg-emerald-900/80 text-emerald-100',
  failed: 'bg-red-900/80 text-red-100',
  cancelled: 'bg-zinc-700 text-zinc-400',
  composing: 'bg-amber-900/80 text-amber-100',
  archived: 'bg-zinc-800 text-zinc-400',
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_CLASS[status] || 'bg-zinc-800 text-zinc-300';
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide ${cls}`}
      data-testid="lvs-status-badge"
    >
      {status}
    </span>
  );
}

export function goLvs(page: string): void {
  window.location.hash =
    page === 'projects' || page === ''
      ? '#/modules/local-video-studio'
      : `#/modules/local-video-studio/${page}`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}
