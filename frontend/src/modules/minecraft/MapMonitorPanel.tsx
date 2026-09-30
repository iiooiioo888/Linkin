/**
 * 地圖監控 — 計畫清單與落地進度。
 */
import { useCallback, useState } from 'react';
import { type MapPlan } from '../../api/linkin';
import { createModuleClient } from '../../api/modules';
import { MiniProgressBar } from '../../components/ui/monitor';
import { McHeader, McLinks, McMetrics, McPage, McPanel } from './McChrome';
import { minecraftHref, statusLabel, useVisibilityPoll } from './monitor/shared';

const mc = createModuleClient('minecraft');

export default function MapMonitorPanel() {
  const [plans, setPlans] = useState<MapPlan[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await mc.get<{ map_plans?: MapPlan[]; count?: number }>('/map/plans');
      setPlans(res.map_plans ?? []);
    } catch {
      try {
        const summary = await mc.get<{ kpis?: { map_plan_count?: number } }>('/minecraft/monitor/summary');
        const planCount = summary.kpis?.map_plan_count ?? 0;
        if (!planCount) setPlans([]);
        else {
          const snap = await mc.get<{ latest_map_plan?: MapPlan | null }>('/minecraft/ai/snapshot');
          setPlans(snap.latest_map_plan ? [snap.latest_map_plan] : []);
        }
      } catch (err) {
        setError((err as Error).message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, 15000);

  const applied = plans.filter((p) => p.status === 'applied').length;
  const partial = plans.filter((p) => p.status === 'partial').length;
  const planned = plans.filter((p) => (p.status ?? 'planned') === 'planned').length;

  return (
    <McPage>
      <McHeader title="地圖" lead="區域計畫、邊界與落地進度。沒有計畫時從敘事工作區生成。" />
      {error ? <p className="mc-error">{error}</p> : null}
      {loading && !plans.length ? <p className="mc-empty">正在讀取地圖計畫…</p> : null}
      {!error ? (
      <McMetrics
        items={[
          { label: '計畫', value: plans.length },
          { label: '已落地', value: applied },
          { label: '部分落地', value: partial },
          { label: '待落地', value: planned },
        ]}
      />
      ) : null}
      <McPanel
        title="地圖計畫"
        action={
          <McLinks
            links={[
              { href: minecraftHref('narrative'), label: '敘事工作區' },
              { href: minecraftHref('layout-preview'), label: '布局預覽', primary: true },
            ]}
          />
        }
      >
        {!error && !loading && !plans.length ? (
          <p className="mc-empty">還沒有地圖計畫。</p>
        ) : (
          <ul className="mc-list">
            {plans.map((plan) => {
              const mcp = (plan as MapPlan & { mcp?: Record<string, unknown> }).mcp;
              const est = plan.estimated_blocks ?? 0;
              const placed = Number(mcp?.blocks_placed ?? 0);
              const pct = est ? Math.round((placed / est) * 100) : 0;
              return (
                <li key={plan.id} className="mc-row">
                  <div className="mc-row__top">
                    <span className="mc-row__title">{plan.title || plan.id}</span>
                    {plan.status ? <span className="mc-row__status">{statusLabel(plan.status)}</span> : null}
                  </div>
                  <p className="mc-row__meta">
                    {[plan.region, `${plan.plots?.length ?? 0} 個地塊`].filter(Boolean).join(' · ')}
                  </p>
                  {plan.bounds ? (
                    <p className="mc-row__meta">
                      ({plan.bounds.x1},{plan.bounds.y1},{plan.bounds.z1}) → ({plan.bounds.x2},{plan.bounds.y2},{plan.bounds.z2})
                    </p>
                  ) : null}
                  {est > 0 ? (
                    <p className="mc-row__meta">
                      方塊 {placed}/{est}
                      {mcp?.dry_run ? ' · 乾跑' : ''}
                    </p>
                  ) : null}
                  {est > 0 ? <MiniProgressBar value={pct} good={pct >= 100} /> : null}
                </li>
              );
            })}
          </ul>
        )}
      </McPanel>
    </McPage>
  );
}
