import { useCallback, useEffect, useState } from 'react';
import {
  listLvsReviewQueue,
  recalledLvsProjectId,
  reviewLvsAsset,
  type LvsReviewQueueItem,
} from '../../lib/localVideoStudioApi';

function go(page: string): void {
  window.location.hash = `#/modules/local-video-studio/${page}`;
}

export default function ReviewPage() {
  const projectId = recalledLvsProjectId();
  const [items, setItems] = useState<LvsReviewQueueItem[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    if (!projectId) return;
    try {
      setItems(await listLvsReviewQueue(projectId));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!projectId) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-[12px] text-[var(--console-sub)]">
        尚未選擇專案。
        <button type="button" className="ml-2 text-[var(--console-accent)] hover:underline" onClick={() => go('projects')}>
          回專案
        </button>
      </div>
    );
  }

  const decide = async (assetId: string, decision: 'approve' | 'reject' | 'needs_retry') => {
    setMessage('');
    try {
      await reviewLvsAsset(assetId, { decision, reason: decision });
      setMessage(`${decision} → ${assetId.slice(0, 8)}`);
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
          <p className="text-[12px] text-[var(--console-sub)]">approve／reject／needs_retry（M4）</p>
        </div>
        <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => go('compose')}>
          合成
        </button>
      </header>
      {message ? <p className="text-[12px] text-[var(--console-accent)]">{message}</p> : null}
      {error ? <p className="text-[12px] text-red-400">{error}</p> : null}
      <ul className="divide-y divide-[var(--console-line)]" data-testid="lvs-review-queue">
        {items.map((item) => (
          <li key={item.asset_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div>
              <p className="text-[13px] text-[var(--console-ink)]">
                {item.asset_type} · {item.relative_path}
              </p>
              <p className="font-mono text-[11px] text-[var(--console-sub)]">
                {item.asset_id.slice(0, 8)} · shot {item.shot_status || '—'} · last {item.last_decision || 'none'}
              </p>
            </div>
            <div className="flex gap-2 text-[12px]">
              <button type="button" className="text-emerald-400 hover:underline" onClick={() => void decide(item.asset_id, 'approve')}>
                通過
              </button>
              <button type="button" className="text-red-400 hover:underline" onClick={() => void decide(item.asset_id, 'reject')}>
                駁回
              </button>
              <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => void decide(item.asset_id, 'needs_retry')}>
                重試
              </button>
            </div>
          </li>
        ))}
        {items.length === 0 ? (
          <li className="py-8 text-center text-[12px] text-[var(--console-sub)]">審核佇列為空</li>
        ) : null}
      </ul>
    </div>
  );
}
