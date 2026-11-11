/** 日志查看弹窗 */
export function LogModal({
  service,
  logs,
  loading,
  onClose,
  onRefresh,
  tail,
  onTailChange,
}: {
  service: string;
  logs: string;
  loading: boolean;
  onClose: () => void;
  onRefresh: () => void;
  tail: number;
  onTailChange: (t: number) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-[var(--console-line)] bg-[var(--console-sidebar)] shadow-2xl">
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-[var(--console-line)] px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-base">📋</span>
            <span className="text-sm font-medium text-[var(--console-ink)]">{service} 日志</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={tail}
              onChange={(e) => onTailChange(Number(e.target.value))}
              className="rounded-md border border-[var(--console-line)] bg-[var(--console-dim)] px-2 py-1 text-[11px] text-[var(--console-sub)]"
            >
              <option value={50}>最近 50 行</option>
              <option value={100}>最近 100 行</option>
              <option value={200}>最近 200 行</option>
              <option value={500}>最近 500 行</option>
            </select>
            <button
              onClick={onRefresh}
              disabled={loading}
              className="rounded-md bg-[var(--console-dim)] px-2.5 py-1 text-[11px] text-[var(--console-faint)] transition-colors hover:bg-gray-700 disabled:opacity-40"
            >
              {loading ? '加载中...' : '🔄 刷新'}
            </button>
            <button
              onClick={onClose}
              className="rounded-md px-2 py-1 text-[var(--console-faint)] transition-colors hover:bg-[var(--console-dim)] hover:text-[var(--console-ink)]"
            >
              ✕
            </button>
          </div>
        </div>

        {/* 日志内容 */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <span className="text-sm text-[var(--console-faint)]">加载中...</span>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-[var(--console-faint)]">
              {logs || '暂无日志'}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
