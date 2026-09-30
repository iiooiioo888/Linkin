/**
 * 建築落地監控 — build-brief 與方塊進度。
 */
import { useCallback, useState } from 'react';
import { fetchBuildBriefs, type BuildBrief } from '../../api/linkin';
import { MiniProgressBar } from '../../components/ui/monitor';
import { McHeader, McMetrics, McPage, McPanel } from './McChrome';
import { statusLabel, useVisibilityPoll } from './monitor/shared';

export default function BuildMonitorPanel() {
  const [briefs, setBriefs] = useState<BuildBrief[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchBuildBriefs();
      setBriefs(res.build_briefs ?? []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, 15000);

  const pending = briefs.filter((b) => (b.status ?? '') === 'pending_builder').length;
  const built = briefs.filter((b) => ['built', 'dispatched'].includes(b.status ?? '')).length;
  const failed = briefs.filter((b) => (b.status ?? '').includes('fail')).length;

  return (
    <McPage>
      <McHeader title="建築落地" lead="敘事提交後產生的建築意圖，以及方塊實際放下的進度。" />
      {error ? <p className="mc-error">{error}</p> : null}
      {loading && !briefs.length ? <p className="mc-empty">正在讀取建築意圖…</p> : null}
      {!error ? (
      <McMetrics
        items={[
          { label: '意圖', value: briefs.length },
          { label: '待建築', value: pending },
          { label: '已落地', value: built },
          { label: '失敗', value: failed },
        ]}
      />
      ) : null}
      <McPanel title="建築意圖">
        {!error && !loading && !briefs.length ? (
          <p className="mc-empty">還沒有建築意圖。在敘事工作區提交後會出現。</p>
        ) : (
          <ul className="mc-list">
            {briefs.map((brief) => {
              const job = brief.build_job;
              const total = job?.blocks_total ?? brief.block_count ?? 0;
              const placed = job?.blocks_placed ?? 0;
              const pct = total ? Math.round((placed / total) * 100) : 0;
              const meta = [brief.region, brief.style].filter(Boolean).join(' · ');
              return (
                <li key={brief.id} className="mc-row">
                  <div className="mc-row__top">
                    <span className="mc-row__title">{brief.title || brief.id}</span>
                    {brief.status ? <span className="mc-row__status">{statusLabel(brief.status)}</span> : null}
                  </div>
                  {meta ? <p className="mc-row__meta">{meta}</p> : null}
                  {total > 0 ? (
                    <>
                      <p className="mc-row__meta">
                        方塊 {placed}/{total}
                        {job?.cancelled ? ' · 已取消' : ''}
                        {job?.dry_run ? ' · 乾跑' : ''}
                      </p>
                      <MiniProgressBar value={pct} good={pct >= 100} />
                    </>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </McPanel>
    </McPage>
  );
}
