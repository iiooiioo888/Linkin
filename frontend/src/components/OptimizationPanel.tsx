/**
 * OptimizationPanel — P0–P3 性能優化路線圖即時監控。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchOptimizationMonitor } from '../api/client';
import type { OptimizationMonitorData } from '../types';
import { RoadmapTable } from './ChatMonitorCards';

export default function OptimizationPanel() {
  const [data, setData] = useState<OptimizationMonitorData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchOptimizationMonitor();
      setData(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 8000);
    return () => clearInterval(timer);
  }, [refresh]);

  const cache = data?.llm_cache;
  const hitPct = Math.round((cache?.hit_rate ?? 0) * 100);
  const routing = data?.routing_feedback;
  const edgeCache = data?.edge_cache ?? data?.opc_edge;

  return (
    <div className="mt-6 border-t border-white/[0.08] pt-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-[var(--console-ink)]">性能優化路線圖</h3>
          <p className="mt-0.5 text-[11px] text-[var(--console-faint)]">
            P0 任務-模型匹配 · 反思早停 · P1 合併審查 · 分層快取 · P2 路由反饋 · 邊緣快取 · P3 Trace
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2 py-1 text-[11px] text-[var(--console-faint)]"
        >
          重新整理
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <RoadmapTable items={data?.roadmap ?? []} />

      <div className="mb-4 mt-4 grid grid-cols-2 gap-2 lg:grid-cols-5">
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] text-[var(--console-faint)]">LLM 快取命中率</p>
          <p className="mt-1 font-mono text-lg text-[var(--console-green)]">{hitPct}%</p>
          <p className="mt-0.5 text-[11px] text-[var(--console-faint)]">
            命中 {cache?.hits ?? 0} · 未中 {cache?.misses ?? 0} · 語義 {cache?.semantic_hits ?? 0}
          </p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] text-[var(--console-faint)]">路由自適應</p>
          <p className="mt-1 font-mono text-lg text-[var(--console-ink)]">{routing?.adaptive_length_threshold ?? '—'}</p>
          <p className="mt-0.5 text-[11px] text-[var(--console-faint)]">
            simple {routing?.simple_count ?? 0} · company {routing?.company_count ?? 0}
          </p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] text-[var(--console-faint)]">反思早停</p>
          <p className="mt-1 text-sm text-[var(--console-ink)]">
            門檻 {data?.reflection.pass_threshold ?? 8} · 最多 {data?.reflection.max_iterations ?? 3} 輪
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--console-faint)]">
            最小提升 Δ{data?.reflection.min_score_improvement ?? 0.5}
          </p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] text-[var(--console-faint)]">Review+Synth</p>
          <p className={`mt-1 text-sm ${data?.merge_review_synth.enabled ? 'text-[var(--console-green)]' : 'text-amber-300'}`}>
            {data?.merge_review_synth.enabled ? '合併模式' : '分離模式'}
          </p>
          <p className="mt-0.5 text-[11px] text-[var(--console-faint)]">EVOL_MERGE_REVIEW_SYNTH</p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] text-[var(--console-faint)]">分層快取</p>
          <p className="mt-1 text-sm text-[var(--console-ink)]">
            {edgeCache?.tier ?? 'exact'} · TTL {edgeCache?.edge_ttl_sec ?? 3600}s
          </p>
          <p className={`mt-0.5 text-[11px] ${edgeCache?.cache_fresh ? 'text-[var(--console-green)]' : 'text-[var(--console-faint)]'}`}>
            {edgeCache?.entry_count ?? 0}/{edgeCache?.max_size ?? 512} 項 · 命中{' '}
            {Math.round((edgeCache?.hit_rate ?? 0) * 100)}%
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-white/[0.08]">
        <p className="border-b border-white/[0.08] bg-[var(--console-card)] px-3 py-2 text-[11px] font-semibold text-[var(--console-faint)]">
          環節 → 模型層級（P0 任務-模型匹配）
        </p>
        <table className="w-full text-left text-[12px]">
          <thead className="bg-[var(--console-bg)] text-[10px] text-[var(--console-faint)]">
            <tr>
              <th className="px-3 py-2 font-medium">環節</th>
              <th className="px-3 py-2 font-medium">Tier</th>
              <th className="px-3 py-2 font-medium">模型</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data?.stage_router ?? {}).map(([stage, info]) => (
              <tr key={stage} className="border-t border-white/[0.08]">
                <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">{stage}</td>
                <td className="px-3 py-1.5 text-[var(--console-accent)]">{info.tier}</td>
                <td className="px-3 py-1.5 font-mono text-[var(--console-faint)]">{info.model}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2 text-[11px] text-[var(--console-faint)]">
        全鏈路 trace：{data?.trace.trace_count ?? 0} 筆任務軌跡 · 詳見「執行軌跡」分頁
      </p>
    </div>
  );
}
