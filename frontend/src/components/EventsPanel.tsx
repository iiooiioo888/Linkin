/**
 * EventsPanel — 雲控制台容器事件時間線。
 *
 * GET /cloud/events：start / stop / restart。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchCloudEvents } from '../api/client';
import { usePagination } from '../lib/pagination';
import type { CloudEvent } from '../types';
import { ConsolePagination } from './ui/ConsolePagination';

function tone(type: string): string {
  if (type === 'start') return 'bg-[#27a644]/15 text-[#4cc38a]';
  if (type === 'stop') return 'bg-red-500/15 text-red-300';
  if (type === 'restart') return 'bg-amber-500/15 text-amber-300';
  return 'bg-[#141516] text-[#8a8f98]';
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || '—';
  return d.toLocaleString('zh-TW', { hour12: false });
}

export default function EventsPanel({ embedded = false }: { embedded?: boolean }) {
  const [events, setEvents] = useState<CloudEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchCloudEvents(80);
      setEvents(data.events ?? []);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  const eventsPager = usePagination(events, embedded ? 5 : events.length || 1);

  const counts = events.reduce<Record<string, number>>((acc, e) => {
    acc[e.type] = (acc[e.type] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className={embedded ? 'space-y-3 text-[#f7f8f8]' : 'flex-1 space-y-4 overflow-auto apple-canvas p-4 text-[#f7f8f8]'}>
      <div className="flex items-center justify-between">
        <div>
          {!embedded ? <h3 className="text-sm font-medium">容器事件時間線</h3> : null}
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">start / stop / restart · 最近 {events.length} 筆</p>
        </div>
        <button
          onClick={() => void refresh()}
          className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
        >
          {loading ? '同步中' : '重新整理'}
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[
          { label: '全部', value: events.length },
          { label: '啟動', value: counts.start ?? 0 },
          { label: '停止', value: counts.stop ?? 0 },
          { label: '重啟', value: counts.restart ?? 0 },
        ].map((kpi) => (
          <div key={kpi.label} className="apple-card apple-card--tight !p-0 px-3 py-2.5">
            <p className="text-[10px] uppercase tracking-wider text-[#62666d]">{kpi.label}</p>
            <p className="mt-1 font-mono text-lg">{kpi.value}</p>
          </div>
        ))}
      </div>

      {events.length === 0 ? (
        <div className="apple-card apple-card--tight !p-0 px-4 py-16 text-center">
          <p className="text-sm text-[#8a8f98]">尚無容器事件</p>
          <p className="mt-1 text-[11px] text-[#62666d]">
            在「實例管理」對容器執行啟動 / 停止 / 重啟後，會寫入 events.jsonl。
          </p>
        </div>
      ) : (
        <div className="relative space-y-0 apple-card apple-card--tight !p-0 p-3">
          {(embedded ? eventsPager.slice : events).map((e, i) => (
            <div key={`${e.ts}-${e.service}-${i}`} className="relative flex gap-3 py-2 pl-4">
              <span className="absolute left-0 top-3 h-full w-px bg-[#23252a]" />
              <span className="absolute left-[-3px] top-3.5 h-1.5 w-1.5 rounded-full bg-[#007AFF]" />
              <span className={`h-fit shrink-0 rounded px-1.5 py-0.5 text-[10px] uppercase ${tone(e.type)}`}>
                {e.type}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-[#d0d6e0]">
                  {e.service}
                  {e.detail ? <span className="text-[#8a8f98]"> · {e.detail}</span> : null}
                </p>
                <p className="mt-0.5 font-mono text-[10px] text-[#62666d]">{fmtTime(e.ts)}</p>
              </div>
            </div>
          ))}
        </div>
      )}
      {embedded && events.length > 0 ? (
        <ConsolePagination page={eventsPager.page} totalPages={eventsPager.pages} onPageChange={eventsPager.setPage} />
      ) : null}
    </div>
  );
}
