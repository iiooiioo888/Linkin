/**
 * 任務進度運行時 — 活躍任務與目標勾選摘要。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchQuestProgressSummary,
  type QuestProgressRow,
} from '../../api/linkin';
import { EmptyStateCta, formatTs, statusLabel, statusStripe } from './monitor/shared';

function ObjectiveChecks({ row }: { row: QuestProgressRow }) {
  const objs = row.objectives_detail || [];
  if (!objs.length) {
    return <span className="text-[var(--console-faint)]">無目標</span>;
  }
  return (
    <ul className="mt-1 space-y-0.5">
      {objs.map((o) => (
        <li key={o.id} className="flex items-start gap-1.5">
          <span className={o.done ? 'text-[var(--console-green)]' : 'text-[var(--console-faint)]'}>
            {o.done ? '✓' : '○'}
          </span>
          <span className={o.done ? 'line-through opacity-70' : ''}>{o.title || o.id}</span>
        </li>
      ))}
    </ul>
  );
}

export function QuestRuntimeStrip({ playerId, compact = false }: { playerId?: string; compact?: boolean }) {
  const [rows, setRows] = useState<QuestProgressRow[]>([]);
  const [stats, setStats] = useState({ active: 0, completed: 0, failed: 0 });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchQuestProgressSummary(12);
      let active = data.active_quests || [];
      if (playerId) {
        active = active.filter((r) => r.player_id?.toLowerCase() === playerId.toLowerCase());
      }
      setRows(active);
      setStats({
        active: data?.active ?? 0,
        completed: data?.completed ?? 0,
        failed: data?.failed ?? 0,
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [playerId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <p className="px-3 py-2 text-xs text-[var(--console-faint)]">載入任務進度…</p>;
  }

  if (error) {
    return <p className="px-3 py-2 text-xs text-[var(--console-red)]">{error}</p>;
  }

  if (!rows.length) {
    return (
      <EmptyStateCta
        title="尚無活躍任務進度"
        hint={
          playerId
            ? '此玩家尚未開始任何任務，或 GM 尚未套用 quest_progress。'
            : '啟用 AI 主持人並套用 quest_progress，或透過 API 手動推進。'
        }
        actions={[
          { label: 'AI 主持人', href: '#/modules/minecraft/ai_gm', primary: true },
          { label: '任務監控', href: '#/modules/minecraft/quest_item_monitor' },
        ]}
      />
    );
  }

  if (compact) {
    return (
      <div className="flex flex-wrap gap-2 px-3 py-2 text-xs">
        {rows.slice(0, 4).map((row) => (
          <span
            key={row.id}
            className="rounded border border-[var(--console-border)] px-2 py-0.5"
            data-priority={statusStripe(row.status || 'active')}
          >
            {row.quest_title || row.quest_id} ({row.objectives_done}/{row.objectives_total})
          </span>
        ))}
        {stats.active > rows.length ? (
          <span className="text-[var(--console-faint)]">+{stats.active - rows.length} 更多</span>
        ) : null}
      </div>
    );
  }

  return (
    <ul className="divide-y divide-[var(--console-border)]">
      {rows.map((row) => (
        <li key={row.id} className="mon-task-card px-3 py-2 text-xs" data-priority={statusStripe(row.status || 'active')}>
          <div className="flex flex-wrap items-baseline justify-between gap-1">
            <span className="font-medium">{row.quest_title || row.quest_id}</span>
            <span className="text-[var(--console-faint)]">
              {statusLabel(row.status || 'active')} · {row.objectives_done}/{row.objectives_total}
            </span>
          </div>
          <div className="mt-0.5 text-[var(--console-faint)]">
            玩家 {row.player_id} · 更新 {formatTs(row.updated_at)}
          </div>
          <ObjectiveChecks row={row} />
        </li>
      ))}
    </ul>
  );
}

export default QuestRuntimeStrip;
