/** HubView — AI Hub 多模型編排操作台。
 *
 * 對齊 docs/AI_HUB_DETAILED_DESIGN.md：同步推論 + Agent 任務輪詢。
 * Linear tokens：canvas #010102 / surface-1 #0f1011 / accent #007AFF。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchHubCatalog,
  hubChatCompletion,
  hubCreateAgentTask,
  hubGetAgentTask,
  HUB_DEV_API_KEY,
} from '../api/client';
import type { HubCatalog, HubChatResult, HubAgentTask, HubModelInfo } from '../api/client';

const STRATEGIES = [
  { value: 'quality_first', label: '品質優先（GPT-5.6 Sol）' },
  { value: 'cost_first', label: '成本優先（DeepSeek）' },
  { value: 'speed_first', label: '速度優先（Gemini × Mercury 競速）' },
  { value: 'manual', label: '手動指定模型' },
] as const;

const REGIONS = [
  { value: 'TW', label: '台灣 TW' },
  { value: 'US', label: '美國 US' },
  { value: 'CN', label: '中國大陸 CN（僅境內模型）' },
] as const;

const SAMPLE_CHAT = '用三句話說明動態權重路由與競速的差異';
const SAMPLE_AGENT = '分析茅台當前估值';

function hubPriceLine(m: HubModelInfo): string {
  if (m.available_in_pool === false) return '鎖定外';
  const extras = [
    m.price_cached_in_per_1m ? `快取 $${m.price_cached_in_per_1m}` : '',
    m.price_cache_write_per_1m ? `寫入 $${m.price_cache_write_per_1m}` : '',
    m.price_reasoning_per_1m ? `推理 $${m.price_reasoning_per_1m}` : '',
    m.price_image_per_1m ? `視覺 $${m.price_image_per_1m}` : '',
    m.price_audio_per_1m ? `音訊 $${m.price_audio_per_1m}` : '',
  ].filter(Boolean);
  const base = `${m.provider} · $${m.price_in_per_1m}/$${m.price_out_per_1m}`;
  return extras.length ? `${base} · ${extras.join(' · ')}` : `${base}/M`;
}

const TOOL_OPTIONS = [
  { id: 'StocksX_get_price', label: 'StocksX 行情' },
  { id: 'StocksX_get_fundamentals', label: 'StocksX 基本面' },
  { id: 'LittleCrawler_fetch', label: 'LittleCrawler 爬蟲' },
  { id: 'StoryForge_draft', label: 'StoryForge 大綱' },
  { id: 'PysdnOPC_read', label: 'PysdnOPC 讀取' },
] as const;

export default function HubView({ embedded = false }: { embedded?: boolean }) {
  const [catalog, setCatalog] = useState<HubCatalog | null>(null);
  const [mode, setMode] = useState<'chat' | 'agent'>('chat');
  const [strategy, setStrategy] = useState('quality_first');
  const [region, setRegion] = useState('TW');
  const [model, setModel] = useState('gpt-5.6-sol');
  const [prompt, setPrompt] = useState(SAMPLE_CHAT);
  const [tools, setTools] = useState<string[]>(['StocksX_get_price']);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatResult, setChatResult] = useState<HubChatResult | null>(null);
  const [agentTask, setAgentTask] = useState<HubAgentTask | null>(null);

  useEffect(() => {
    fetchHubCatalog(HUB_DEV_API_KEY)
      .then(setCatalog)
      .catch(() => setCatalog(null));
  }, []);

  useEffect(() => {
    const usable = (catalog?.models ?? []).filter((m) => m.available_in_pool !== false);
    if (usable.length > 0 && !usable.some((m) => m.id === model)) {
      setModel(usable[0].id);
    }
  }, [catalog, model]);

  const runChat = useCallback(async () => {
    setBusy(true);
    setError(null);
    setChatResult(null);
    try {
      const result = await hubChatCompletion({
        prompt,
        strategy,
        region,
        model: strategy === 'manual' ? model : undefined,
      });
      setChatResult(result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [prompt, strategy, region, model]);

  const runAgent = useCallback(async () => {
    setBusy(true);
    setError(null);
    setAgentTask(null);
    try {
      const created = await hubCreateAgentTask({
        input: prompt,
        tools: tools.length ? tools : undefined,
        strategy,
        region,
      });
      let latest = await hubGetAgentTask(created.task_id);
      setAgentTask(latest);
      const deadline = Date.now() + 30_000;
      while (
        (latest.status === 'queued' || latest.status === 'running') &&
        Date.now() < deadline
      ) {
        await new Promise((r) => setTimeout(r, 400));
        latest = await hubGetAgentTask(created.task_id);
        setAgentTask(latest);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [prompt, strategy, region, tools]);

  const onSubmit = () => {
    if (mode === 'chat') void runChat();
    else void runAgent();
  };

  const content =
    chatResult?.choices?.[0]?.message?.content || agentTask?.result?.content || '';
  const usableModels = (catalog?.models ?? []).filter((m) => m.available_in_pool !== false);

  return (
    <div className="flex h-full min-h-0 flex-col apple-canvas text-[var(--console-ink)]">
      {!embedded && (
        <div className="border-b border-white/[0.08] px-5 py-3">
          <h1 className="text-sm font-semibold tracking-tight">AI Hub 多模型編排</h1>
          <p className="mt-0.5 text-[11px] text-[var(--console-sub)]">
            {catalog?.pool_lock?.lock_message
              || '旗艦 GPT-5.6 Sol · 多模態 Gemini 3.1 Pro · 不含 Anthropic / Claude'}
          </p>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-0 lg:grid-cols-[minmax(280px,360px)_1fr]">
        <section className="overflow-y-auto border-b border-white/[0.08] p-4 lg:border-b-0 lg:border-r">
          <div className="mb-3 flex gap-1 rounded-lg bg-[var(--console-card)] p-1">
            <button
              className={`flex-1 rounded-md px-2 py-1.5 text-xs ${
                mode === 'chat' ? 'bg-[var(--console-blue)] text-white' : 'text-[var(--console-sub)]'
              }`}
              onClick={() => {
                setMode('chat');
                setPrompt(SAMPLE_CHAT);
              }}
            >
              同步推論
            </button>
            <button
              className={`flex-1 rounded-md px-2 py-1.5 text-xs ${
                mode === 'agent' ? 'bg-[var(--console-blue)] text-white' : 'text-[var(--console-sub)]'
              }`}
              onClick={() => {
                setMode('agent');
                setPrompt(SAMPLE_AGENT);
              }}
            >
              Agent 任務
            </button>
          </div>

          <label className="mb-2 block text-[11px] text-[var(--console-sub)]">路由策略</label>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            className="mb-3 w-full rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2 py-1.5 text-xs"
          >
            {STRATEGIES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>

          <label className="mb-2 block text-[11px] text-[var(--console-sub)]">屬地</label>
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="mb-3 w-full rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2 py-1.5 text-xs"
          >
            {REGIONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>

          {strategy === 'manual' && (
            <>
              <label className="mb-2 block text-[11px] text-[var(--console-sub)]">模型</label>
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="mb-3 w-full rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2 py-1.5 text-xs"
              >
                {(usableModels.length ? usableModels : [{ id: 'gpt-5.6-sol' }]).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.id}
                    {'provider' in m ? ` · ${m.provider}` : ''}
                  </option>
                ))}
              </select>
            </>
          )}

          {mode === 'agent' && (
            <div className="mb-3">
              <p className="mb-2 text-[11px] text-[var(--console-sub)]">工具（可多選；寫入 OPC 禁止）</p>
              <div className="space-y-1">
                {TOOL_OPTIONS.map((opt) => (
                  <label key={opt.id} className="flex items-center gap-2 text-[11px] text-[#d0d6e0]">
                    <input
                      type="checkbox"
                      checked={tools.includes(opt.id)}
                      onChange={() => {
                        setTools((prev) =>
                          prev.includes(opt.id)
                            ? prev.filter((id) => id !== opt.id)
                            : [...prev, opt.id],
                        );
                      }}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>
          )}

          <label className="mb-2 block text-[11px] text-[var(--console-sub)]">提示詞</label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={6}
            className="mb-3 w-full resize-y rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2 py-1.5 text-xs leading-relaxed"
          />

          <button
            onClick={onSubmit}
            disabled={busy || !prompt.trim()}
            className="w-full rounded-md bg-[var(--console-blue)] px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            {busy ? '編排中…' : mode === 'chat' ? '送出推論' : '建立 Agent 任務'}
          </button>

          {catalog && (
            <div className="mt-4">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[var(--console-faint)]">
                模型目錄（灰字＝目前 API 不可用）
              </p>
              <ul className="space-y-1">
                {catalog.models.map((m) => (
                  <li
                    key={m.id}
                    className={`flex items-center justify-between rounded border border-white/[0.08] bg-[var(--console-card)] px-2 py-1 text-[11px] ${
                      m.available_in_pool === false ? 'opacity-40' : ''
                    }`}
                  >
                    <span className="text-[#d0d6e0]">{m.id}</span>
                    <span className="max-w-[220px] truncate text-right text-[var(--console-faint)]" title={hubPriceLine(m)}>
                      {hubPriceLine(m)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <section className="flex min-h-0 flex-col overflow-y-auto p-4">
          {error && (
            <div className="mb-3 rounded-md border border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-3 py-2 text-xs console-status-danger">
              {error}
            </div>
          )}

          {(chatResult || agentTask) && (
            <div className="mb-3 flex flex-wrap gap-2 text-[11px]">
              <Meta
                label="廠商"
                value={chatResult?.chosen_provider || agentTask?.chosen_provider || '—'}
              />
              <Meta
                label="模型"
                value={chatResult?.model || agentTask?.result?.model || '—'}
              />
              <Meta
                label="費用"
                value={`$${(chatResult?.cost_usd ?? agentTask?.cost_usd ?? 0).toFixed(6)}`}
              />
              <Meta
                label="延遲"
                value={`${chatResult?.latency_ms ?? agentTask?.latency_ms ?? 0} ms`}
              />
              <Meta
                label="切換"
                value={String(chatResult?.failover_hops ?? agentTask?.result?.failover_hops ?? 0)}
              />
              {chatResult?.cache && <Meta label="快取" value={chatResult.cache} />}
              {agentTask?.trace_id && <Meta label="Trace" value={agentTask.trace_id.slice(0, 12)} />}
            </div>
          )}

          {chatResult?.notice && (
            <p className="mb-3 text-xs console-status-amber">{chatResult.notice}</p>
          )}

          {agentTask?.result?.tool_traces && agentTask.result.tool_traces.length > 0 && (
            <div className="mb-3 apple-card apple-card--tight !p-0 p-3">
              <p className="mb-2 text-[11px] font-medium text-[var(--console-sub)]">工具追蹤</p>
              {agentTask.result.tool_traces.map((t, i) => (
                <pre
                  key={`${t.tool}-${i}`}
                  className="mb-1 overflow-x-auto text-[11px] text-[#d0d6e0]"
                >
                  {t.tool} · {t.http_status} · {t.latency_ms}ms
                  {'\n'}
                  {JSON.stringify(t.data ?? {}, null, 2)}
                </pre>
              ))}
            </div>
          )}

          <div className="min-h-[160px] flex-1 apple-card apple-card--tight !p-0 p-4">
            {content ? (
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-[#d0d6e0]">{content}</p>
            ) : (
              <p className="text-xs text-[var(--console-faint)]">
                結果會顯示於此。Agent 會依工具呼叫 StocksX / LittleCrawler / StoryForge / PysdnOPC
                讀取，再由 GPT-5.6 Sol 生成；限流則降級 Qwen3.5-Max。工業寫入必須走 opc_service 護欄。
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-full border border-white/[0.08] bg-[var(--console-card)] px-2.5 py-0.5 text-[var(--console-sub)]">
      {label} <span className="text-[var(--console-ink)]">{value}</span>
    </span>
  );
}
