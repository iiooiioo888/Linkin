/**
 * TraceRoster — 執行軌跡清單（SidePanel 與 TraceView 共用）。
 */
import { useCallback, useEffect, useState } from 'react';
import { Virtuoso } from 'react-virtuoso';
import { fetchTraces } from '../api/client';
import type { TraceSummary } from '../types';

interface TraceRosterProps {
  selectedTaskId: string | null;
  onPick: (taskId: string) => void;
}

export default function TraceRoster({ selectedTaskId, onPick }: TraceRosterProps) {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const loadTraces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTraces(50);
      setTraces(data.traces);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTraces();
    const t = setInterval(() => void loadTraces(), 8000);
    return () => clearInterval(t);
  }, [loadTraces]);

  const filtered = traces.filter((t) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return t.task_id.toLowerCase().includes(q);
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 space-y-2 border-b border-white/[0.06] px-3 pb-3 pt-2">
        <div className="flex items-center justify-between">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#636366]">
            {traces.length} 筆軌跡
          </p>
          <button
            type="button"
            onClick={() => void loadTraces()}
            disabled={loading}
            className="rounded-lg px-1.5 py-0.5 text-[10px] text-[#636366] hover:bg-white/[0.04] hover:text-[#AEAEB2] disabled:opacity-40"
            title="重新整理"
          >
            {loading ? '…' : '↻'}
          </button>
        </div>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜尋任務 ID"
          className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[11px] text-[#F5F5F7] placeholder:text-[#636366] outline-none focus:border-[#007AFF]/50"
        />
      </div>

      {error && (
        <p className="shrink-0 px-3 py-2 text-[10px] text-[#FF3B30]">{error}</p>
      )}

      {!loading && filtered.length === 0 && (
        <p className="px-3 py-8 text-center text-[11px] text-[#636366]">
          {traces.length === 0 ? '尚無軌跡記錄' : '無符合結果'}
        </p>
      )}

      {filtered.length > 0 && (
        <Virtuoso
          className="min-h-0 flex-1"
          data={filtered}
          itemContent={(_i, trace: TraceSummary) => {
            const active = trace.task_id === selectedTaskId;
            return (
              <button
                type="button"
                onClick={() => onPick(trace.task_id)}
                className={`mx-2 mb-0.5 flex w-[calc(100%-16px)] flex-col gap-0.5 rounded-lg px-2.5 py-2 text-left transition-colors ${
                  active
                    ? 'bg-white/[0.06] text-[#F5F5F7]'
                    : 'text-[#AEAEB2] hover:bg-white/[0.03] hover:text-[#F5F5F7]'
                }`}
              >
                <span className="truncate font-mono text-[11px] text-[#007AFF]">{trace.task_id}</span>
                <span className="text-[10px] text-[#636366]">
                  {trace.event_count} 事件 · {trace.file_size_kb} KB
                </span>
              </button>
            );
          }}
        />
      )}
    </div>
  );
}
