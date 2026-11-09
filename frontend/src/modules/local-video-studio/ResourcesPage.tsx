import { useEffect, useState } from 'react';
import {
  getLvsResources,
  listLvsAssets,
  recalledLvsProjectId,
  type LvsAsset,
  type LvsResourceSummary,
} from '../../lib/localVideoStudioApi';
import { formatBytes, goLvs } from './ui';

export default function ResourcesPage() {
  const projectId = recalledLvsProjectId();
  const [summary, setSummary] = useState<LvsResourceSummary | null>(null);
  const [assets, setAssets] = useState<LvsAsset[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!projectId) return;
    void Promise.all([getLvsResources(projectId), listLvsAssets(projectId)])
      .then(([r, a]) => {
        setSummary(r);
        setAssets(a);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [projectId]);

  if (!projectId) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-[12px] text-[var(--console-sub)]">
        尚未選擇專案
      </div>
    );
  }

  const discardedRatio =
    summary && summary.attempts > 0
      ? ((summary.discarded_count / summary.attempts) * 100).toFixed(1)
      : '0.0';

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-resources-page">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">資源消耗</h2>
          <p className="text-[12px] text-[var(--console-sub)]">硬體分鐘 · 廢片比 · 儲存（不寫「成本」）</p>
        </div>
        <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => goLvs('detail')}>
          詳情
        </button>
      </header>

      {error ? <p className="text-[12px] text-red-400">{error}</p> : null}

      {summary ? (
        <dl className="grid max-w-lg grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-[12px]" data-testid="lvs-resources">
          <dt className="text-[var(--console-sub)]">GPU 分鐘</dt>
          <dd className="text-[var(--console-ink)]">{summary.gpu_minutes}</dd>
          <dt className="text-[var(--console-sub)]">牆鐘分鐘</dt>
          <dd className="text-[var(--console-ink)]">{summary.wall_minutes}</dd>
          <dt className="text-[var(--console-sub)]">嘗試／廢片</dt>
          <dd className="text-[var(--console-ink)]">
            {summary.attempts} / {summary.discarded_count}（{discardedRatio}%）
          </dd>
          <dt className="text-[var(--console-sub)]">儲存</dt>
          <dd className="text-[var(--console-ink)]">{formatBytes(summary.storage_bytes)}</dd>
          <dt className="text-[var(--console-sub)]">API 呼叫</dt>
          <dd className="text-[var(--console-ink)]">{summary.api_calls}</dd>
          <dt className="text-[var(--console-sub)]">任務／資產</dt>
          <dd className="text-[var(--console-ink)]">
            {summary.job_count} / {summary.asset_count}
          </dd>
        </dl>
      ) : !error ? (
        <p className="text-[12px] text-[var(--console-sub)]">載入中…</p>
      ) : null}

      <section>
        <h3 className="mb-2 text-[13px] font-medium text-[var(--console-ink)]">資產清單</h3>
        <ul className="divide-y divide-[var(--console-line)] text-[12px]">
          {assets.map((a) => (
            <li key={a.id} className="flex justify-between gap-3 py-2 text-[var(--console-ink)]">
              <span>
                {a.type} · <span className="font-mono text-[11px] text-[var(--console-sub)]">{a.relative_path}</span>
              </span>
              <span className="text-[var(--console-sub)]">{formatBytes(a.bytes || 0)}</span>
            </li>
          ))}
          {assets.length === 0 ? (
            <li className="py-6 text-center text-[var(--console-sub)]">尚無資產</li>
          ) : null}
        </ul>
      </section>
    </div>
  );
}
