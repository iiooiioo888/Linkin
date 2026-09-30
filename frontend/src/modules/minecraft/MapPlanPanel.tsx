/**
 * 地圖計畫 — 區域地圖 generate / preview / apply（世界與建築）。
 */
import { useCallback, useState } from 'react';
import {
  applyMapPlan,
  generateMapPlan,
  previewMapPlan,
  type MapPlan,
  type MapPlanPreview,
} from '../../api/linkin';
import { McHeader, McLinks, McPage, McPanel } from './McChrome';

export default function MapPlanPanel() {
  const [region, setRegion] = useState('织庭都');
  const [seed, setSeed] = useState('');
  const [plan, setPlan] = useState<MapPlan | null>(null);
  const [preview, setPreview] = useState<MapPlanPreview | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const onGenerate = async () => {
    setBusy('generate');
    setError(null);
    setMessage(null);
    try {
      const res = await generateMapPlan({ region, seed: seed || undefined });
      setPlan(res.plan);
      setPreview(res.preview);
      setMessage(`已生成 ${res.plan.id}（${res.source}）`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onPreview = async () => {
    if (!plan) return;
    setBusy('preview');
    setError(null);
    try {
      const res = await previewMapPlan({ plan_id: plan.id });
      setPreview(res.preview);
      setMessage('預覽已更新');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onApply = async () => {
    if (!plan) return;
    setBusy('apply');
    setError(null);
    try {
      const res = await applyMapPlan({ plan_id: plan.id, confirm: true });
      setPlan(res.plan);
      setMessage(`落地狀態：${res.status}${res.minecraft?.dry_run ? ' (dry-run)' : ''}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const loadLatest = useCallback(async () => {
    try {
      const { createModuleClient } = await import('../../api/modules');
      const mc = createModuleClient('minecraft');
      const res = await mc.get<{ map_plans: MapPlan[] }>('/map/plans');
      if (res.map_plans?.[0]) {
        setPlan(res.map_plans[0]);
        setPreview(null);
      }
    } catch {
      // 忽略
    }
  }, []);

  const facts = plan
    ? [
        { label: '區域', value: plan.region },
        { label: '狀態', value: plan.status || '已計畫' },
        { label: '地塊', value: String(plan.plots.length) },
        ...(plan.estimated_blocks ? [{ label: '方塊', value: String(plan.estimated_blocks) }] : []),
        ...(preview ? [{ label: '預覽地塊', value: String(preview.plot_count) }] : []),
      ]
    : [];

  return (
    <McPage>
      <McHeader
        title="地圖計畫"
        lead="依區域生成地圖，先預覽再落地。也可以到布局預覽看俯視圖。"
      />
      <div className="mc-workspace">
        {error ? <p className="mc-error">{error}</p> : null}
        {message ? <p className="mc-note">{message}</p> : null}
        <McPanel title="生成">
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              區域
              <input className="mt-1 w-full rounded-xl border px-3 py-2" value={region} onChange={(e) => setRegion(e.target.value)} />
            </label>
            <label>
              種子（可留空）
              <input className="mt-1 w-full rounded-xl border px-3 py-2" value={seed} onChange={(e) => setSeed(e.target.value)} />
            </label>
          </div>
          <div className="mc-actions">
            <button type="button" className="mc-btn is-primary" disabled={!!busy} onClick={() => void onGenerate()}>
              {busy === 'generate' ? '生成中' : '生成'}
            </button>
            <button type="button" className="mc-btn" disabled={!plan || !!busy} onClick={() => void onPreview()}>
              預覽
            </button>
            <button type="button" className="mc-btn" disabled={!plan || !!busy} onClick={() => void onApply()}>
              落地
            </button>
            <button type="button" className="mc-btn" onClick={() => void loadLatest()}>
              載入最新
            </button>
          </div>
          <McLinks links={[{ href: '#/modules/minecraft/layout-preview', label: '布局預覽' }]} />
        </McPanel>
        {plan ? (
          <McPanel title={plan.title || plan.region} hint={plan.id}>
            {plan.summary ? <p className="mc-note">{plan.summary}</p> : null}
            <dl className="mc-facts">
              {facts.map((fact) => (
                <div key={fact.label}>
                  <dt>{fact.label}</dt>
                  <dd>{fact.value}</dd>
                </div>
              ))}
            </dl>
            {preview?.pois?.length ? (
              <ul className="mc-list" style={{ marginTop: 12 }}>
                {preview.pois.slice(0, 8).map((poi) => (
                  <li key={poi.id} className="mc-row">
                    <div className="mc-row__top">
                      <span className="mc-row__title">{poi.title}</span>
                      <span className="mc-row__meta">{poi.kind}</span>
                    </div>
                    <span className="mc-row__meta">{poi.location}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </McPanel>
        ) : (
          <p className="mc-empty">還沒有地圖計畫。填區域後生成，或從敘事工作區帶入。</p>
        )}
      </div>
    </McPage>
  );
}
