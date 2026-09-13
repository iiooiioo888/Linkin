/**
 * 四維情境快照 — 市況／經濟／地土／玩家（唯讀 Phase 1）
 */
import { useCallback, useState } from 'react';
import { fetchMinecraftSituation, type MinecraftSituationSnapshot } from '../../api/linkin';
import { formatTs, statusLabel, useVisibilityPoll } from './monitor/shared';

const DIM_LABELS: Record<string, string> = {
  market: '市況',
  economy: '經濟',
  land: '地土',
  players: '玩家',
};

function statusTone(status: string): string {
  if (status === 'ok') return 'text-[var(--console-green)]';
  if (status === 'partial') return 'text-[var(--console-amber)]';
  return 'text-[var(--console-faint)]';
}

function DimCell({
  keyName,
  block,
}: {
  keyName: string;
  block: { status?: string; summary?: string; confidence?: number };
}) {
  const label = DIM_LABELS[keyName] || keyName;
  const status = block?.status || 'unknown';
  return (
    <div className="min-w-0 flex-1 rounded border border-[var(--console-border)] bg-[var(--console-surface)] px-2 py-1.5">
      <div className="flex items-center justify-between gap-1">
        <span className="text-[10px] font-medium text-[#c9a961]">{label}</span>
        <span className={`text-[9px] ${statusTone(status)}`}>{statusLabel(status)}</span>
      </div>
      <p className="mt-0.5 line-clamp-2 text-[9px] text-[var(--console-sub)]">{block?.summary || '—'}</p>
      {typeof block?.confidence === 'number' ? (
        <span className="text-[8px] text-[var(--console-faint)]">信心 {Math.round(block.confidence * 100)}%</span>
      ) : null}
    </div>
  );
}

type SituationStripProps = {
  compact?: boolean;
  pollMs?: number;
};

export default function SituationStrip({ compact = false, pollMs = 15000 }: SituationStripProps) {
  const [data, setData] = useState<MinecraftSituationSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const snap = await fetchMinecraftSituation();
      setData(snap);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, pollMs);

  if (error) {
    return <p className="text-[10px] text-[var(--console-red)]">情境快照：{error}</p>;
  }

  if (!data && loading) {
    return <p className="text-[10px] text-[var(--console-faint)]">載入情境快照…</p>;
  }

  if (!data) {
    return <p className="text-[10px] text-[var(--console-faint)]">情境快照不可用</p>;
  }

  const dims = ['market', 'economy', 'land', 'players'] as const;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] font-medium text-[var(--console-ink)]">四維情境</span>
        <button type="button" className="console-btn-ghost text-[9px]" onClick={() => void load()} disabled={loading}>
          {loading ? '刷新中…' : `更新 ${formatTs(data.generated_at)}`}
        </button>
      </div>
      <div className={`flex gap-2 ${compact ? 'flex-col sm:flex-row' : 'flex-col md:flex-row'}`}>
        {dims.map((key) => (
          <DimCell key={key} keyName={key} block={data[key]} />
        ))}
      </div>
      {!compact && data.hints?.length ? (
        <ul className="list-inside list-disc space-y-0.5 text-[9px] text-[var(--console-faint)]">
          {data.hints.slice(0, 4).map((hint) => (
            <li key={hint}>{hint}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
