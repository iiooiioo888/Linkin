import { useEffect, useMemo, useState } from 'react';
import LcBarChart from '../../components/charts/LcBarChart';
import LcLineChart from '../../components/charts/LcLineChart';
import { consoleLayout } from '../../lib/consoleLayout';
import { fetchMediaVaultMonitorSummary, type MediaVaultMonitorSummary } from '../../lib/mediaVaultApi';

type Props = {
  moduleId: string;
  page: string;
  focusBatchId?: string;
  onOpenGalleryBatch?: (batchId: string) => void;
};

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function MonitorPanel({ focusBatchId, onOpenGalleryBatch }: Props) {
  const [data, setData] = useState<MediaVaultMonitorSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchMediaVaultMonitorSummary()
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  const ingestSeries = useMemo(() => {
    if (!data?.ingest_series_24h.length) return [];
    return [
      {
        id: 'ingest',
        name: '入庫',
        color: '#60a5fa',
        points: data.ingest_series_24h.map((b, i) => ({ x: i, y: b.count })),
      },
    ];
  }, [data]);

  const complianceCategories = useMemo(
    () => data?.compliance_distribution.map((r) => r.label) ?? [],
    [data],
  );
  const complianceGroups = useMemo(
    () =>
      data?.compliance_distribution.length
        ? [{ subCategory: '貼文數', values: data.compliance_distribution.map((r) => r.count) }]
        : [],
    [data],
  );

  if (error) {
    return (
      <p className="p-4 text-[12px] text-red-400" data-testid="media-vault-monitor">
        監控載入失敗：{error}
      </p>
    );
  }

  if (!data) {
    return (
      <p className="p-4 text-[12px] text-[var(--console-sub)]" data-testid="media-vault-monitor">
        載入監控…
      </p>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="media-vault-monitor">
      {focusBatchId ? (
        <p className="text-[11px] text-[var(--console-sub)]">
          聚焦批次：<span className="font-mono text-[var(--console-ink)]">{focusBatchId}</span>
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="今日入庫" value={String(data.today_ingested)} testId="media-vault-stat-today" />
        <StatCard label="總貼文" value={String(data.total_posts)} />
        <StatCard
          label="任務成功率"
          value={data.success_rate != null ? `${Math.round(data.success_rate * 100)}%` : '—'}
        />
        <StatCard label="dedup 碰撞率" value={`${Math.round(data.dedup_collision_rate * 100)}%`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className={`${consoleLayout.insetCard} p-3`}>
          <h2 className="mb-2 text-[12px] font-medium text-[var(--console-ink)]">24h 入庫速率</h2>
          {ingestSeries.length ? (
            <LcLineChart series={ingestSeries} height={200} />
          ) : (
            <p className="text-[11px] text-[var(--console-sub)]">尚無資料</p>
          )}
        </section>
        <section className={`${consoleLayout.insetCard} p-3`}>
          <h2 className="mb-2 text-[12px] font-medium text-[var(--console-ink)]">合規分布</h2>
          {complianceCategories.length ? (
            <LcBarChart categories={complianceCategories} groups={complianceGroups} height={200} />
          ) : (
            <p className="text-[11px] text-[var(--console-sub)]">尚無資料</p>
          )}
        </section>
      </div>

      <section className="rounded-lg border border-[var(--console-line)] p-3">
        <h2 className="mb-2 text-[12px] font-medium text-[var(--console-ink)]">儲存（依平台）</h2>
        <ul className="space-y-1 text-[11px]">
          {data.storage_by_platform.map((row) => (
            <li key={row.platform} className="flex justify-between text-[var(--console-sub)]">
              <span>{row.platform || 'unknown'}</span>
              <span>{formatBytes(Number(row.bytes))}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-lg border border-[var(--console-line)] p-3">
        <h2 className="mb-2 text-[12px] font-medium text-[var(--console-ink)]">近期失敗任務</h2>
        <table className="w-full text-left text-[11px]">
          <thead className="text-[var(--console-sub)]">
            <tr>
              <th className="py-1">job_id</th>
              <th>platform</th>
              <th>error</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.mediacrawler_failures.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-2 text-[var(--console-sub)]">
                  無失敗紀錄
                </td>
              </tr>
            ) : (
              data.mediacrawler_failures.map((row) => (
                <tr key={row.job_id} className="border-t border-[var(--console-line)]">
                  <td className="py-1 font-mono">{row.job_id}</td>
                  <td>{row.platform}</td>
                  <td className="max-w-xs truncate">{row.error}</td>
                  <td>
                    {onOpenGalleryBatch && row.job_id ? (
                      <button
                        type="button"
                        className="text-[var(--console-accent)] hover:underline"
                        onClick={() => onOpenGalleryBatch(row.job_id!)}
                      >
                        畫廊
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {data.ingest_errors.length ? (
        <section className="rounded-lg border border-[var(--console-line)] p-3">
          <h2 className="mb-2 text-[12px] font-medium text-[var(--console-ink)]">入庫錯誤</h2>
          <ul className="max-h-40 space-y-1 overflow-y-auto text-[10px] text-[var(--console-sub)]">
            {data.ingest_errors.map((e) => (
              <li key={e.id}>
                [{e.created_at}] {e.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, testId }: { label: string; value: string; testId?: string }) {
  return (
    <div className={`${consoleLayout.insetCard} p-3`} data-testid={testId}>
      <p className="text-[10px] uppercase tracking-wide text-[var(--console-sub)]">{label}</p>
      <p className="text-[20px] font-semibold text-[var(--console-ink)]">{value}</p>
    </div>
  );
}
