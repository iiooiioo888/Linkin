/**
 * 地圖監控 — map plans、預覽／落地狀態、方塊估算。
 */
import { useCallback, useEffect, useState } from 'react';
import { type MapPlan } from '../../api/linkin';
import { createModuleClient } from '../../api/modules';
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

const mc = createModuleClient('minecraft');

export default function MapMonitorPanel() {
  const [plans, setPlans] = useState<MapPlan[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await mc.get<{ map_plans: MapPlan[]; count: number }>('/map/plans');
      setPlans(res.map_plans ?? []);
    } catch {
      try {
        const summary = await mc.get<{ kpis: { map_plan_count: number } }>('/minecraft/monitor/summary');
        if (!summary.kpis.map_plan_count) setPlans([]);
        else {
          const snap = await mc.get<{ latest_map_plan: MapPlan | null }>('/minecraft/ai/snapshot');
          setPlans(snap.latest_map_plan ? [snap.latest_map_plan] : []);
        }
      } catch (err) {
        setError((err as Error).message);
      }
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const applied = plans.filter((p) => p.status === 'applied').length;
  const partial = plans.filter((p) => p.status === 'partial').length;
  const planned = plans.filter((p) => (p.status ?? 'planned') === 'planned').length;

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          <KpiGrid6>
            <KpiSparkCard label="計畫總數" value={String(plans.length)} accent />
            <KpiSparkCard label="已落地" value={String(applied)} />
            <KpiSparkCard label="部分" value={String(partial)} />
            <KpiSparkCard label="待落地" value={String(planned)} />
          </KpiGrid6>

          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>地圖計畫 · generate / preview / apply</ConsoleCardHeader>
            {!plans.length ? (
              <div className="space-y-2 px-3 pb-3 text-xs text-[var(--console-faint)]">
                <p>尚無地圖計畫 — 請在「地圖計畫」或敘事工作區生成。</p>
                <div className="flex flex-wrap gap-2">
                  <a href="#/modules/minecraft/narrative" className="console-btn-ghost">敘事工作區</a>
                  <a href="#/modules/minecraft/layout-preview" className="console-btn-ghost">布局預覽</a>
                </div>
              </div>
            ) : (
              <ul className="divide-y divide-[var(--console-border)]">
                {plans.map((plan) => {
                  const stripe = statusStripe(plan.status ?? 'planned');
                  const mcp = (plan as MapPlan & { mcp?: Record<string, unknown> }).mcp;
                  const est = plan.estimated_blocks ?? 0;
                  const placed = Number(mcp?.blocks_placed ?? 0);
                  const pct = est ? Math.round((placed / est) * 100) : 0;
                  return (
                    <li key={plan.id} className="mon-task-card px-3 py-3 text-xs" data-priority={stripe}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="font-medium text-[var(--console-text)]">{plan.title || plan.id}</div>
                          <div className="text-[var(--console-faint)]">{plan.region} · {plan.plots?.length ?? 0} plots</div>
                        </div>
                        <span className="text-[var(--console-accent)]">{statusLabel(plan.status ?? 'planned')}</span>
                      </div>
                      <div className="mt-2 grid gap-1 text-[var(--console-muted)]">
                        <div>邊界：({plan.bounds?.x1},{plan.bounds?.y1},{plan.bounds?.z1}) → ({plan.bounds?.x2},{plan.bounds?.y2},{plan.bounds?.z2})</div>
                        <div>預估方塊：{est} {mcp?.dry_run ? '· dry-run' : ''}</div>
                      </div>
                      {est > 0 ? (
                        <div className="mt-2">
                          <p className="mb-1 text-[9px] text-[var(--console-faint)]">落地進度</p>
                          <MiniProgressBar value={pct} good={pct >= 100} />
                        </div>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            )}
          </ConsoleCard>

          {plans.length > 0 ? (
            <div className="mt-2 text-right">
              <a href="#/modules/minecraft/layout-preview" className="console-btn-ghost text-xs">
                本地布局預覽
              </a>
            </div>
          ) : null}
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
