/**
 * 建築落地監控 — build-brief jobs、方塊、取消／partial。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchBuildBriefs, type BuildBrief } from '../../api/linkin';
import { KpiSparkCard, MiniProgressBar } from '../../components/ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  KpiGrid6,
  PanelAlert,
  PanelShell,
} from '../../components/ui/ConsoleLayout';
import { statusLabel, statusStripe } from './monitor/shared';

export default function BuildMonitorPanel() {
  const [briefs, setBriefs] = useState<BuildBrief[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchBuildBriefs();
      setBriefs(res.build_briefs);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const pending = briefs.filter((b) => (b.status ?? '') === 'pending_builder').length;
  const built = briefs.filter((b) => ['built', 'dispatched'].includes(b.status ?? '')).length;
  const failed = briefs.filter((b) => (b.status ?? '').includes('fail')).length;

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          <KpiGrid6>
            <KpiSparkCard label="意圖總數" value={String(briefs.length)} accent />
            <KpiSparkCard label="待建築" value={String(pending)} />
            <KpiSparkCard label="已落地" value={String(built)} />
            <KpiSparkCard label="失敗" value={String(failed)} />
          </KpiGrid6>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>Build Brief 任務</ConsoleCardHeader>
            {!briefs.length ? (
              <p className="px-3 pb-3 text-xs text-[var(--console-faint)]">尚無建築意圖 — 請在敘事工作區 commit 後產生。</p>
            ) : (
              <ul className="divide-y divide-[var(--console-border)]">
                {briefs.map((brief) => {
                  const job = brief.build_job;
                  const total = job?.blocks_total ?? brief.block_count ?? 0;
                  const placed = job?.blocks_placed ?? 0;
                  const pct = total ? Math.round((placed / total) * 100) : 0;
                  return (
                    <li key={brief.id} className="mon-task-card px-3 py-3 text-xs" data-priority={statusStripe(brief.status ?? 'pending_builder')}>
                      <div className="flex justify-between gap-2">
                        <div>
                          <div className="font-medium">{brief.title || brief.id}</div>
                          <div className="text-[var(--console-faint)]">{brief.region} · {brief.style}</div>
                        </div>
                        <span className="text-[var(--console-accent)]">{statusLabel(brief.status ?? 'pending_builder')}</span>
                      </div>
                      {job ? (
                        <div className="mt-2">
                          <p className="mb-1 text-[9px] text-[var(--console-faint)]">方塊 {placed}/{total}</p>
                          <MiniProgressBar value={pct} good={pct >= 100} />
                          {job.cancelled ? <div className="mt-1 text-[var(--console-red)]">已取消</div> : null}
                          {job.dry_run ? <div className="text-[var(--console-amber)]">dry-run</div> : null}
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </ConsoleCard>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
