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
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  PanelAlert,
  PanelShell,
} from '../../components/ui/ConsoleLayout';

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

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          {message ? <p className="mb-2 text-xs text-[var(--console-green)]">{message}</p> : null}
          <ConsoleCard>
            <ConsoleCardHeader>地圖計畫 · Phase 4 區域地圖</ConsoleCardHeader>
            <div className="grid gap-2 px-3 pb-3 text-xs">
              <label className="grid gap-1">
                <span className="text-[var(--console-faint)]">區域</span>
                <input className="console-input" value={region} onChange={(e) => setRegion(e.target.value)} />
              </label>
              <label className="grid gap-1">
                <span className="text-[var(--console-faint)]">Seed（可選）</span>
                <input className="console-input" value={seed} onChange={(e) => setSeed(e.target.value)} />
              </label>
              <div className="flex flex-wrap gap-2 pt-1">
                <button type="button" className="console-btn" disabled={!!busy} onClick={() => void onGenerate()}>
                  {busy === 'generate' ? '生成中…' : '生成'}
                </button>
                <button type="button" className="console-btn-ghost" disabled={!plan || !!busy} onClick={() => void onPreview()}>
                  預覽
                </button>
                <button type="button" className="console-btn-ghost" disabled={!plan || !!busy} onClick={() => void onApply()}>
                  落地（confirm）
                </button>
                <button type="button" className="console-btn-ghost" onClick={() => void loadLatest()}>
                  載入最新
                </button>
              </div>
            </div>
          </ConsoleCard>
          {plan ? (
            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>
                {plan.title || plan.id} · {plan.region} · {plan.status ?? 'planned'}
              </ConsoleCardHeader>
              <pre className="max-h-64 overflow-auto px-3 pb-3 text-[10px] text-[var(--console-muted)]">
                {JSON.stringify({ plan, preview }, null, 2)}
              </pre>
            </ConsoleCard>
          ) : (
            <p className="mt-3 text-xs text-[var(--console-faint)]">尚無計畫 — 可從敘事工作區帶入上下文後生成。</p>
          )}
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
