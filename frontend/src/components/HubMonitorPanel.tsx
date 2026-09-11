/**
 * HubMonitorPanel — 監控中心 AI Hub 多方編排。
 *
 * 九模型探針、熔斷狀態、語義快取、日預算、呼叫日誌。零 Claude。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchHubMonitor } from '../api/client';
import { HUB_FALLBACK_MODELS, HUB_FALLBACK_ROUTING } from '../lib/monitorFallbacks';
import type { HubMonitorData } from '../types';
import {
  ConsoleCard,
  ConsoleCardHeader,
  KpiGrid,
  PanelAlert,
  PanelSection,
  PanelShell,
  SectionHeader,
  consoleLayout,
} from './ui/ConsoleLayout';

function circuitTone(state: string): string {
  if (state === 'OPEN') return 'bg-red-500/15 console-status-danger';
  if (state === 'HALF_OPEN') return 'bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)] console-status-amber';
  return 'bg-[#27a644]/15 text-[#4cc38a]';
}

function statusTone(status: string): string {
  if (status === 'success') return 'text-[#4cc38a]';
  if (status === 'filtered' || status === 'budget_denied') return 'console-status-amber';
  return 'console-status-danger';
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

export default function HubMonitorPanel({ embedded = false }: { embedded?: boolean }) {
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

  const body = (
      <PanelSection>
        {!embedded ? (
          <SectionHeader
            title="AI Hub 編排監控"
            description={
              data?.routing?.pool_lock?.lock_message
                || 'GPT-5.6 Sol 旗艦 · Gemini 3.1 Pro 多模態 · 禁止 Anthropic / Claude'
            }
            actions={
              <button type="button" onClick={() => void refresh()} className={consoleLayout.refreshBtn}>
                {loading ? '同步中' : '重新整理'}
              </button>
            }
          />
        ) : (
          <div className="flex justify-end">
            <button type="button" onClick={() => void refresh()} className={consoleLayout.refreshBtn}>
              {loading ? '同步中' : '重新整理'}
            </button>
          </div>
        )}

        {error ? <PanelAlert>{error}</PanelAlert> : null}

        <KpiGrid>
        <div className={consoleLayout.kpiCard}>
          <p className={consoleLayout.kpiLabel}>語義快取命中率</p>
          <p className="mt-1 font-mono text-lg">{hitPct}%</p>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-[var(--console-card)]">
            <div className="h-full bg-[var(--console-blue)]" style={{ width: `${hitPct}%` }} />
          </div>
          <p className="mt-1 text-[10px] text-[var(--console-faint)]">目標 &gt; {targetPct}%</p>
        </div>
        <div className={consoleLayout.kpiCard}>
          <p className={consoleLayout.kpiLabel}>今日預算</p>
          <p className="mt-1 font-mono text-lg">
            {fmtUsd(budget?.spent_today_usd)}
            <span className="text-xs text-[var(--console-faint)]"> / {fmtUsd(budget?.daily_limit_usd)}</span>
          </p>
          <div className="mt-2 h-1 overflow-hidden rounded-full bg-[var(--console-card)]">
            <div
              className="h-full"
              style={{
                width: `${spentPct}%`,
                background: spentPct >= 90 ? '#e5484d' : 'var(--console-blue)',
              }}
            />
          </div>
        </div>
        <div className={consoleLayout.kpiCard}>
          <p className={consoleLayout.kpiLabel}>呼叫日誌</p>
          <p className="mt-1 font-mono text-lg">{data?.call_log_count ?? 0}</p>
          <p className="mt-1 text-[10px] text-[var(--console-faint)]">上游 {data?.upstream_calls ?? 0} 次</p>
        </div>
        <div className={consoleLayout.kpiCard}>
          <p className={consoleLayout.kpiLabel}>熔斷 Open</p>
          <p className="mt-1 font-mono text-lg">
            {models.filter((m) => m.circuit.state === 'OPEN').length}
          </p>
          <p className="mt-1 text-[10px] text-[var(--console-faint)]">threshold 50% · 半開 10s</p>
        </div>
        </KpiGrid>

        <ConsoleCard>
          <ConsoleCardHeader className="mb-0 border-b-0 bg-transparent px-3 pt-3 pb-1.5">故障轉移鏈</ConsoleCardHeader>
          <div className="px-3 pb-3">
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {(routing.default_chain).map(
            (id, i, arr) => (
              <span key={id} className="flex items-center gap-1.5">
                <span className="rounded-full border border-white/[0.08] bg-[var(--console-card)] px-2 py-0.5 text-[#d0d6e0]">
                  {id}
                </span>
                {i < arr.length - 1 && <span className="text-[var(--console-faint)]">→</span>}
              </span>
            ),
          )}
        </div>
        <p className="mt-2 text-[10px] text-[var(--console-faint)]">
          CN 僅 {routing.cn_chain.join(' / ') || 'DeepSeek / Qwen / MiMo'} · 競速{' '}
          {routing.race_pair.join(' × ') || 'Gemini × Mercury'} · 禁止{' '}
          {routing.forbidden_vendor}
        </p>
          </div>
        </ConsoleCard>

        <ConsoleCard className="overflow-x-auto">
        <table className="w-full min-w-[1040px] text-left">
          <thead>
            <tr className="border-b border-white/[0.08] text-[10px] uppercase tracking-wider text-[var(--console-faint)]">
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
                  <p className="text-xs text-[var(--console-ink)]">{m.id}</p>
                  <p className="text-[10px] text-[var(--console-faint)]">{m.provider}</p>
                </td>
                <td className="px-3 py-2 text-[11px]">
                  {m.available_in_pool === false ? (
                    <span className="text-[var(--console-faint)]">不可用</span>
                  ) : (
                    <span className="text-[#4cc38a]">{m.mapped_model || '可用'}</span>
                  )}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{m.intelligence}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 overflow-hidden rounded-full bg-[var(--console-card)]">
                      <div
                        className="h-full bg-[var(--console-blue)]"
                        style={{
                          width: `${Math.min(100, ((Number(m.latency_ewma_ms) || 0) / maxLatency) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="font-mono text-[11px] text-[var(--console-sub)]">
                      {Math.round(Number(m.latency_ewma_ms) || 0)} ms
                    </span>
                  </div>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-[var(--console-sub)]">
                  {m.ttfb_ms != null ? `${Math.round(Number(m.ttfb_ms))} ms` : '—'}
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-[var(--console-sub)]">
                  ${Number(m.price_in_per_1m ?? 0).toFixed(3)} / ${Number(m.price_out_per_1m ?? 0).toFixed(3)}
                </td>
                <td className="px-3 py-2 text-[11px] text-[var(--console-sub)]">{extraPriceBits(m) || '—'}</td>
                <td className="px-3 py-2 font-mono text-[11px]">{m.consecutive_fail}</td>
                <td className="px-3 py-2 font-mono text-[11px] text-[var(--console-sub)]">
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
        </ConsoleCard>

        <div className={consoleLayout.cardGrid}>
          <ConsoleCard>
            <ConsoleCardHeader className="mb-0 border-b-0 bg-transparent px-3 pt-3 pb-1.5">呼叫日誌</ConsoleCardHeader>
            <div className="px-3 pb-3">
          {(data?.call_logs.length ?? 0) === 0 ? (
            <p className="text-[11px] text-[var(--console-faint)]">
              尚無推論紀錄。到 AI Hub 送出一次同步推論後會寫入 call_logs。
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {data!.call_logs.map((log, i) => (
                <div
                  key={`${log.id ?? i}`}
                  className="flex items-center justify-between gap-2 rounded-md bg-[var(--console-card)] px-2 py-1.5 text-[11px]"
                >
                  <span className="min-w-0 truncate text-[#d0d6e0]">
                    {log.model_name} · {log.provider}
                  </span>
                  <span className="shrink-0 font-mono text-[var(--console-sub)]">
                    {fmtUsd(log.cost_usd)} · {log.latency_ms ?? '—'}ms
                  </span>
                  <span className={`shrink-0 ${statusTone(log.status ?? '')}`}>
                    {log.status}
                  </span>
                </div>
              ))}
            </div>
          )}
            </div>
          </ConsoleCard>

          <ConsoleCard>
            <ConsoleCardHeader className="mb-0 border-b-0 bg-transparent px-3 pt-3 pb-1.5">Agent 任務</ConsoleCardHeader>
            <div className="px-3 pb-3">
          {(data?.agent_tasks.length ?? 0) === 0 ? (
            <p className="text-[11px] text-[var(--console-faint)]">
              尚無 Agent 任務。工具呼叫走 JWT RPC，OPC 寫入禁止直連。
            </p>
          ) : (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {data!.agent_tasks.map((t) => (
                <div key={t.task_id} className="rounded-md bg-[var(--console-card)] px-2 py-1.5 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="text-[#d0d6e0]">{t.status}</span>
                    <span className="font-mono text-[var(--console-sub)]">{fmtUsd(t.cost_usd)}</span>
                  </div>
                  <p className="mt-0.5 truncate text-[var(--console-sub)]">{t.input}</p>
                </div>
              ))}
            </div>
          )}
            </div>
          </ConsoleCard>
        </div>
      </PanelSection>
  );

  if (embedded) return body;
  return <PanelShell>{body}</PanelShell>;
}
