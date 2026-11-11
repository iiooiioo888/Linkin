/**
 * 任務階段進度條：執行中流光、已通過階段藍線、失敗紅線。
 */

export function PhaseProgress({
  phases,
  currentIdx,
  running,
  failed,
}: {
  phases: { key: string; label: string }[];
  currentIdx: number;
  running: boolean;
  failed: boolean;
}) {
  const phasePassed = (i: number) => (failed ? i < currentIdx : i < currentIdx || (!running && i <= currentIdx));
  return (
      <div className="mt-2.5 flex items-center gap-1">
        {phases.map((p, i) => {
          const active = running && i === currentIdx;
          return (
            <div key={p.key} className="flex flex-1 flex-col items-center gap-1">
              <div
                className={`h-1.5 w-full rounded-full transition-colors duration-300 ${
                  failed && i === currentIdx
                    ? 'bg-red-500'
                    : phasePassed(i)
                      ? 'bg-blue-500'
                      : active
                        ? 'progress-shimmer'
                        : 'bg-[var(--console-line)]'
                }`}
              />
              <span
                className={`whitespace-nowrap text-[10px] ${
                  active ? 'console-status-blue' : phasePassed(i) ? 'text-[var(--console-sub)]' : 'text-gray-600'
                }`}
              >
                {p.label}
              </span>
            </div>
          );
        })}
      </div>
  );
}
