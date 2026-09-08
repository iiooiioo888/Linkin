/**
 * HubMonitorPanel — 監控中心 AI Hub 多方編排。
 *
 * 九模型探針、熔斷狀態、語義快取、日預算、呼叫日誌。零 Claude。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchHubMonitor } from '../api/client';
import { HUB_FALLBACK_MODELS, HUB_FALLBACK_ROUTING } from '../lib/monitorFallbacks';
import type { HubMonitorData } from '../types';

function circuitTone(state: string): string {
  if (state === 'OPEN') return 'bg-red-500/15 text-red-300';
  if (state === 'HALF_OPEN') return 'bg-amber-500/15 text-amber-300';
  return 'bg-[#27a644]/15 text-[#4cc38a]';
}

function statusTone(status: string): string {
  if (status === 'success') return 'text-[#4cc38a]';
  if (status === 'filtered' || status === 'budget_denied') return 'text-amber-300';
  return 'text-red-300';
}

function extraPriceBits(m: {
  price_cached_in_per_1m?: number | null;
  price_cache_write_per_1m?: number | null;
  price_reasoning_per_1m?: number | null;
  price_image_per_1m?: number | null;
  price_audio_per_1m?: number | null;
}): string {
  return [
    m.price_cached_in_per_1m ? `快取 $${Number(m.price_cached_in_per_1m).toFixed(3)}` : '',
    m.price_cache_write_per_1m ? `寫入 $${Number(m.price_cache_write_per_1m).toFixed(3)}` : '',
    m.price_reasoning_per_1m ? `推理 $${Number(m.price_reasoning_per_1m).toFixed(3)}` : '',
    m.price_image_per_1m ? `視覺 $${Number(m.price_image_per_1m).toFixed(3)}` : '',
    m.price_audio_per_1m ? `音訊 $${Number(m.price_audio_per_1m).toFixed(3)}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
}

function fmtUsd(n: number | undefined): string {
  const v = n ?? 0;
  if (v < 0.01) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(3)}`;
}

export default function HubMonitorPanel() {
  const [data, setData] = useState<HubMonitorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchHubMonitor();
      setData(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 8000);
    return () => clearInterval(timer);
  }, [refresh]);

  const cache = data?.cache;
  const hitPct = Math.round((cache?.hit_rate ?? 0) * 100);
  const targetPct = Math.round((cache?.target_hit_rate ?? 0.4) * 100);
  const budget = data?.budgets[0];
  const models = data?.models && data.models.length > 0 ? data.models : HUB_FALLBACK_MODELS;
  const routing = data?.routing ?? HUB_FALLBACK_ROUTING;
  const spentPct =
    budget && budget.daily_limit_usd > 0
      ? Math.min(100, (budget.spent_today_usd / budget.daily_limit_usd) * 100)
      : 0;
  const maxLatency = Math.max(1, ...models.map((m) => Number(m.latency_ewma_ms) || 0));

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">AI Hub 編排監控</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            {data?.routing?.pool_lock?.lock_message
              || 'GPT-5.6 Sol 旗艦 · Gemini 3.1 Pro 多模態 · 禁止 Anthropic / Claude'}
          </p>
        </div>
        <button
          onClick={() => void refresh()}
          className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
        >
          {loading ? '同步中' : '重新整理'}
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">語義快取命中率</p>
          <p className="mt-1 font-mono text-lg">{hitPct}%</p>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-[#141516]">
            <div className="h-full bg-[#007AFF]" style={{ width: `${hitPct}%` }} />
          </div>
          <p className="mt-1 text-[10px] text-[#62666d]">目標 &gt; {targetPct}%</p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">今日預算</p>
          <p className="mt-1 font-mono text-lg">
            {fmtUsd(budget?.spent_today_usd)}
            <span className="text-xs text-[#62666d]"> / {fmtUsd(budget?.daily_limit_usd)}</span>
          </p>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-[#141516]">
            <div
              className="h-full"
              style={{
                width: `${spentPct}%`,
                background: spentPct >= 90 ? '#e5484d' : '#007AFF',
              }}
            />
          </div>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">呼叫日誌</p>
          <p className="mt-1 font-mono text-lg">{data?.call_log_count ?? 0}</p>
          <p className="mt-1 text-[10px] text-[#62666d]">上游 {data?.upstream_calls ?? 0} 次</p>
        </div>
        <div className="apple-card apple-card--tight !p-0 px-3 py-2.5">
          <p className="text-[10px] uppercase tracking-wider text-[#62666d]">熔斷 Open</p>
          <p className="mt-1 font-mono text-lg">
            {models.filter((m) => m.circuit.state === 'OPEN').length}
          </p>
          <p className="mt-1 text-[10px] text-[#62666d]">threshold 50% · 半開 10s</p>
        </div>
      </div>

      <section className="mb-4 apple-card apple-card--tight !p-0 p-3">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
          故障轉移鏈
        </p>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {(routing.default_chain).map(
            (id, i, arr) => (
              <span key={id} className="flex items-center gap-1.5">
                <span className="rounded-full border border-white/[0.08] bg-[#141516] px-2 py-0.5 text-[#d0d6e0]">
                  {id}
                </span>
                {i < arr.length - 1 && <span className="text-[#62666d]">→</span>}
              </span>
            ),
          )}
        </div>
        <p className="mt-2 text-[10px] text-[#62666d]">
          CN 僅 {routing.cn_chain.join(' / ') || 'DeepSeek / Qwen / MiMo'} · 競速{' '}
          {routing.race_pair.join(' × ') || 'Gemini × Mercury'} · 禁止{' '}
          {routing.forbidden_vendor}
        </p>
      </section>

      <div className="mb-4 overflow-x-auto apple-card apple-card--tight !p-0">
        <table className="w-full min-w-[1040px] text-left">
          <thead>
            <tr className="border-b border-white/[0.08] text-[10px] uppercase tracking-wider text-[#62666d]">
              <th className="px-3 py-2 font-medium">模型</th>
              <th className="px-3 py-2 font-medium">目前 API</th>
              <th className="px-3 py-2 font-medium">智能分</th>
              <th className="px-3 py-2 font-medium">延遲 EWMA</th>
              <th className="px-3 py-2 font-medium">TTFB</th>
              <th className="px-3 py-2 font-medium">輸入 / 輸出</th>
              <th className="px-3 py-2 font-medium">其他收費</th>
              <th className="px-3 py-2 font-medium">連續失敗</th>
              <th className="px-3 py-2 font-medium">錯誤率</th>
              <th className="px-3 py-2 font-medium">熔斷</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr
                key={m.id}
                className={`border-b border-white/[0.08] last:border-0 ${
                  m.available_in_pool === false ? 'opacity-40' : ''
                }`}
              >
                <td className="px-3 py-2">
                  <p className="text-xs text-[#f7f8f8]">{m.id}</p>
                  <p className="text-[10px] text-[#62666d]">{m.provider}</p>
                </td>
                <td className="px-3 py-2 text-[11px]">
                  {m.available_in_pool === false ? (
                    <span className="text-[#62666d]">不可用</span>
                  ) : (
                    <span className="text-[#4cc38a]">{m.mapped_model || '可用'}</span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{m.intelligence}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[#141516]">
                      <div
                        className="h-full bg-[#007AFF]"
                        style={{
                          width: `${Math.min(100, ((Number(m.latency_ewma_ms) || 0) / maxLatency) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="font-mono text-[11px] text-[#8a8f98]">
                      {Math.round(Number(m.latency_ewma_ms) || 0)} ms
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-[#8a8f98]">
                  {m.ttfb_ms != null ? `${Math.round(Number(m.ttfb_ms))} ms` : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-[#8a8f98]">
                  ${Number(m.price_in_per_1m ?? 0).toFixed(3)} / ${Number(m.price_out_per_1m ?? 0).toFixed(3)}
                </td>
                <td className="px-3 py-2 text-[11px] text-[#8a8f98]">{extraPriceBits(m) || '—'}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{m.consecutive_fail}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-[#8a8f98]">
                  {m.circuit.fail_ratio != null
                    ? `${Math.round(Number(m.circuit.fail_ratio) * 100)}%`
                    : '—'}
                  {m.circuit.window_calls != null ? ` / ${m.circuit.window_calls}` : ''}
                </td>
                <td className="px-3 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-[10px] ${circuitTone(m.circuit.state)}`}>
                    {m.circuit.state}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="apple-card apple-card--tight !p-0 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
            呼叫日誌
          </p>
          {(data?.call_logs.length ?? 0) === 0 ? (
            <p className="text-[11px] text-[#62666d]">
              尚無推論紀錄。到 AI Hub 送出一次同步推論後會寫入 call_logs。
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {data!.call_logs.map((log, i) => (
                <div
                  key={`${log.id ?? i}`}
                  className="flex items-center justify-between gap-2 rounded-md bg-[#141516] px-2 py-1.5 text-[11px]"
                >
                  <span className="min-w-0 truncate text-[#d0d6e0]">
                    {log.model_name} · {log.provider}
                  </span>
                  <span className="shrink-0 font-mono text-[#8a8f98]">
                    {fmtUsd(log.cost_usd)} · {log.latency_ms ?? '—'}ms
                  </span>
                  <span className={`shrink-0 ${statusTone(log.status ?? '')}`}>
                    {log.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="apple-card apple-card--tight !p-0 p-3">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
            Agent 任務
          </p>
          {(data?.agent_tasks.length ?? 0) === 0 ? (
            <p className="text-[11px] text-[#62666d]">
              尚無 Agent 任務。工具呼叫走 JWT RPC，OPC 寫入禁止直連。
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {data!.agent_tasks.map((t) => (
                <div key={t.task_id} className="rounded-md bg-[#141516] px-2 py-1.5 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[#d0d6e0]">{t.status}</span>
                    <span className="font-mono text-[#8a8f98]">{fmtUsd(t.cost_usd)}</span>
                  </div>
                  <p className="mt-0.5 truncate text-[#8a8f98]">{t.input}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
