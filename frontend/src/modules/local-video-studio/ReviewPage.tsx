import { useCallback, useEffect, useState } from 'react';
import {
  listLvsReviewQueue,
  lvsAssetMediaUrl,
  recalledLvsProjectId,
  reviewLvsAsset,
  type LvsReviewQueueItem,
} from '../../lib/localVideoStudioApi';
import { StatusBadge, goLvs } from './ui';

export default function ReviewPage() {
  const projectId = recalledLvsProjectId();
  const [items, setItems] = useState<LvsReviewQueueItem[]>([]);
  const [selected, setSelected] = useState<LvsReviewQueueItem | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const rows = await listLvsReviewQueue(projectId);
    setItems(rows);
    setSelected((prev) => {
      if (prev && rows.some((r) => r.asset_id === prev.asset_id)) {
        return rows.find((r) => r.asset_id === prev.asset_id) || rows[0] || null;
      }
      return rows[0] || null;
    });
    setError('');
  }, [projectId]);

  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [refresh]);

  if (!projectId) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-[12px] text-[var(--console-sub)]">
        尚未選擇專案。
        <button type="button" className="ml-2 text-[var(--console-accent)] hover:underline" onClick={() => goLvs('projects')}>
          回專案
        </button>
      </div>
    );
  }

  const decide = async (decision: 'approve' | 'reject' | 'needs_retry') => {
    if (!selected) return;
    setMessage('');
    setError('');
    try {
      await reviewLvsAsset(selected.asset_id, {
        decision,
        reason: reason.trim() || decision,
      });
      setMessage(`${decision} → ${selected.asset_id.slice(0, 8)}`);
      setReason('');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-review">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">審核</h2>
          <p className="text-[12px] text-[var(--console-sub)]">待審佇列 · 影片播放 · 通過／駁回／需重試</p>
        </div>
        <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => goLvs('compose')}>
          合成
        </button>
      </header>

      {message ? <p className="text-[12px] text-[var(--console-accent)]">{message}</p> : null}
      {error ? <p className="text-[12px] text-red-400">{error}</p> : null}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[16rem_1fr]">
        <ul className="divide-y divide-[var(--console-line)] border border-[var(--console-line)]" data-testid="lvs-review-queue">
          {items.map((item) => (
            <li key={item.asset_id}>
              <button
                type="button"
                className={`flex w-full flex-col items-start gap-1 px-3 py-2 text-left text-[12px] ${
                  selected?.asset_id === item.asset_id ? 'bg-[var(--console-accent)]/10' : ''
                }`}
                onClick={() => setSelected(item)}
              >
                <span className="text-[var(--console-ink)]">
                  {item.asset_type} · {item.relative_path.split('/').pop()}
                </span>
                <span className="font-mono text-[10px] text-[var(--console-sub)]">
                  {item.asset_id.slice(0, 8)} · last {item.last_decision || 'none'}
                </span>
                {item.shot_status ? <StatusBadge status={item.shot_status} /> : null}
              </button>
            </li>
          ))}
          {items.length === 0 ? (
            <li className="px-3 py-8 text-center text-[12px] text-[var(--console-sub)]">審核佇列為空</li>
          ) : null}
        </ul>

        <div className="flex flex-col gap-3">
          {selected ? (
            <>
              <video
                key={selected.asset_id}
                src={lvsAssetMediaUrl(selected.asset_id)}
                controls
                className="max-h-[28rem] w-full bg-black"
                data-testid="lvs-review-player"
              />
              <p className="font-mono text-[11px] text-[var(--console-sub)]">{selected.relative_path}</p>
              <label className="flex flex-col gap-1 text-[11px] text-[var(--console-sub)]">
                Reason
                <input
                  className="rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px] text-[var(--console-ink)]"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="可選"
                  data-testid="lvs-review-reason"
                />
              </label>
              <div className="flex gap-3 text-[12px]">
                <button type="button" className="text-emerald-400 hover:underline" onClick={() => void decide('approve')}>
                  通過
                </button>
                <button type="button" className="text-red-400 hover:underline" onClick={() => void decide('reject')}>
                  駁回
                </button>
                <button
                  type="button"
                  className="text-[var(--console-accent)] hover:underline"
                  onClick={() => void decide('needs_retry')}
                >
                  需重試
                </button>
              </div>
            </>
          ) : (
            <p className="text-[12px] text-[var(--console-sub)]">選擇左側資產以播放</p>
          )}
        </div>
      </div>
    </div>
  );
}
