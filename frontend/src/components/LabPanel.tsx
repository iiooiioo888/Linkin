/**
 * 實驗室面板 — Firecrawl · Prompt Optimizer · Archify · Ponytail · 策略庫 · 策略圖 · MCP · A/B。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ArchifyIR, FirecrawlScrapeResult, PonytailReviewResult } from '../api/client';
import { labArchifyEvoloop, labArchifyGenerate, labFirecrawlScrape, labFirecrawlSearch, labOptimizePrompt, labPonytailReview } from '../api/client';
import { LAB_INTEGRATION_TABS, LAB_TABS, type LabSubTab } from '../lib/labTabs';
import { activityNavPath } from '../lib/monitorTabs';
import { extractMarkdownImages } from '../lib/visualCards';
import ArchifyFrame from './ArchifyFrame';
import LcBarChart from './charts/LcBarChart';
import MediaGallery from './media/MediaGallery';
import PromptEditor from './PromptEditor';
import StrategyCatalogPanel from './StrategyCatalogPanel';
import StrategyMapPanel from './StrategyMapPanel';
import ErrorState from './ui/ErrorState';

const DEMO_BEFORE = `你是一位工業助手。根據感測資料回答問題。
請盡量詳細說明。`;

const MCP_TOOLS = [
  { id: 'opc.read', name: 'OPC Read', desc: '讀取白名單標籤', enabled: true, risk: 'low' },
  { id: 'opc.write', name: 'OPC Write', desc: '經護欄寫入', enabled: true, risk: 'high' },
  { id: 'memory.search', name: 'Memory Search', desc: '向量記憶檢索', enabled: true, risk: 'low' },
  { id: 'firecrawl.scrape', name: 'Firecrawl Scrape', desc: '網頁 → Markdown', enabled: true, risk: 'mid' },
  { id: 'docker.inspect', name: 'Docker Inspect', desc: '容器狀態查詢', enabled: false, risk: 'mid' },
];

const AB_SERIES = [
  { name: '準確', a: 7.2, b: 8.6 },
  { name: '完整', a: 6.8, b: 8.1 },
  { name: '清晰', a: 7.5, b: 8.4 },
  { name: '相關', a: 7.0, b: 8.9 },
  { name: '延遲↓', a: 4.2, b: 6.8 },
];

function tabBtn(active: boolean) {
  return `shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold transition-colors ${
    active ? 'bg-[#007AFF] text-white' : 'bg-white/[0.04] text-[#AEAEB2] hover:text-[#F5F5F7]'
  }`;
}

function UpstreamLink({ name, url }: { name: string; url: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[10px] text-[#8E8E93] transition-colors hover:border-[#007AFF]/40 hover:text-[#007AFF]"
    >
      {name} ↗
    </a>
  );
}

interface LabPanelProps {
  activeTab: LabSubTab;
  onTabChange: (tab: LabSubTab) => void;
}

export default function LabPanel({ activeTab, onTabChange }: LabPanelProps) {
  const tab = activeTab;
  const tabMeta = LAB_TABS.find((t) => t.key === tab);

  // Prompt Optimizer
  const [before, setBefore] = useState(DEMO_BEFORE);
  const [after, setAfter] = useState('');
  const [promptMode, setPromptMode] = useState<'user' | 'system'>('user');
  const [promptGoal, setPromptGoal] = useState('更簡潔、可執行');
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptError, setPromptError] = useState<string | null>(null);

  // Firecrawl
  const [fcUrl, setFcUrl] = useState('https://docs.firecrawl.dev');
  const [fcQuery, setFcQuery] = useState('EvoLoop AI agent');
  const [fcScrape, setFcScrape] = useState<FirecrawlScrapeResult | null>(null);
  const [fcSearchMarkdown, setFcSearchMarkdown] = useState('');
  const [fcLoading, setFcLoading] = useState(false);
  const [fcError, setFcError] = useState<string | null>(null);

  // Archify
  const [archIr, setArchIr] = useState<ArchifyIR | null>(null);
  const [archDesc, setArchDesc] = useState('Browser -> FastAPI -> LangGraph -> LiteLLM -> Redis/Chroma');
  const [archLoading, setArchLoading] = useState(false);
  const [archError, setArchError] = useState<string | null>(null);

  // Ponytail
  const [reviewInput, setReviewInput] = useState(
    'import flatpickr from "flatpickr";\nexport function DateField() {\n  return <input ref={(el) => flatpickr(el)} />;\n}',
  );
  const [reviewKind, setReviewKind] = useState<'code' | 'prompt' | 'diff'>('code');
  const [reviewResult, setReviewResult] = useState<PonytailReviewResult | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const [tools, setTools] = useState(MCP_TOOLS);

  const winner = useMemo(() => {
    const scoreA = AB_SERIES.reduce((s, r) => s + r.a, 0) / AB_SERIES.length;
    const scoreB = AB_SERIES.reduce((s, r) => s + r.b, 0) / AB_SERIES.length;
    return { scoreA, scoreB, better: scoreB >= scoreA ? 'B' : 'A' };
  }, []);

  const scrapeImages = useMemo(
    () => (fcScrape ? extractMarkdownImages(fcScrape.markdown, fcScrape.url) : []),
    [fcScrape],
  );

  const loadEvoloopArch = useCallback(async () => {
    setArchLoading(true);
    setArchError(null);
    try {
      setArchIr(await labArchifyEvoloop());
    } catch (err) {
      setArchError((err as Error).message);
    } finally {
      setArchLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'archify' && !archIr && !archLoading) {
      void loadEvoloopArch();
    }
  }, [tab, archIr, archLoading, loadEvoloopArch]);

  const runPromptOptimize = async () => {
    setPromptLoading(true);
    setPromptError(null);
    try {
      const result = await labOptimizePrompt({
        prompt: before,
        mode: promptMode,
        goal: promptGoal,
      });
      setAfter(result.optimized);
    } catch (err) {
      setPromptError((err as Error).message);
    } finally {
      setPromptLoading(false);
    }
  };

  const runFirecrawlScrape = async () => {
    setFcLoading(true);
    setFcError(null);
    try {
      setFcScrape(await labFirecrawlScrape(fcUrl));
    } catch (err) {
      setFcError((err as Error).message);
    } finally {
      setFcLoading(false);
    }
  };

  const runFirecrawlSearch = async () => {
    setFcLoading(true);
    setFcError(null);
    try {
      const result = await labFirecrawlSearch(fcQuery, 5);
      const merged = result.results
        .map((r) => `## ${r.title}\n${r.url}\n\n${r.markdown}`)
        .join('\n\n---\n\n');
      setFcSearchMarkdown(merged || result.hint || '無結果');
    } catch (err) {
      setFcError((err as Error).message);
    } finally {
      setFcLoading(false);
    }
  };

  const runArchifyGenerate = async () => {
    setArchLoading(true);
    setArchError(null);
    try {
      setArchIr(await labArchifyGenerate(archDesc));
    } catch (err) {
      setArchError((err as Error).message);
    } finally {
      setArchLoading(false);
    }
  };

  const runPonytailReview = async () => {
    setReviewLoading(true);
    setReviewError(null);
    try {
      setReviewResult(await labPonytailReview(reviewInput, reviewKind));
    } catch (err) {
      setReviewError((err as Error).message);
    } finally {
      setReviewLoading(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
      {/* 行動端分頁列（桌面由左側 LabSidebar 導航） */}
      <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-white/[0.06] px-4 py-3 md:hidden">
        {LAB_TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => onTabChange(item.key)}
            className={tabBtn(tab === item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
        {/* 整合工具概覽（僅四大工具分頁顯示） */}
        {LAB_INTEGRATION_TABS.some((t) => t.key === tab) && (
          <div className="mx-auto mb-5 flex max-w-5xl flex-wrap gap-2 md:hidden">
            {LAB_INTEGRATION_TABS.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => onTabChange(item.key)}
                className={`rounded-xl border px-3 py-2 text-left transition-colors ${
                  tab === item.key
                    ? 'border-[#007AFF]/50 bg-[#007AFF]/10'
                    : 'border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]'
                }`}
              >
                <span className="block text-[12px] font-bold text-[#F5F5F7]">{item.label}</span>
                {item.upstream && (
                  <span className="mt-0.5 block text-[10px] text-[#636366]">{item.upstream.name}</span>
                )}
              </button>
            ))}
          </div>
        )}

        {tabMeta?.upstream && (
          <div className="mx-auto mb-4 flex max-w-5xl items-center gap-2">
            <UpstreamLink name={tabMeta.upstream.name} url={tabMeta.upstream.url} />
            <span className="text-[10px] text-[#48484A]">
              {tab === 'quant' ? '角色 tool_call 引用' : tab === 'maps' ? 'Archify 可視化 · 角色可引用' : '後端 API · LLM 經 call_llm'}
            </span>
          </div>
        )}

        {tab === 'prompt' && (
          <div className="mx-auto max-w-5xl space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={promptMode}
                onChange={(e) => setPromptMode(e.target.value as 'user' | 'system')}
                className="rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#F5F5F7]"
              >
                <option value="user">User 提示詞</option>
                <option value="system">System 提示詞</option>
              </select>
              <input
                value={promptGoal}
                onChange={(e) => setPromptGoal(e.target.value)}
                placeholder="優化目標"
                className="min-w-[180px] flex-1 rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-3 py-1.5 text-[12px] text-[#F5F5F7]"
              />
              <button
                type="button"
                disabled={promptLoading}
                onClick={() => void runPromptOptimize()}
                className="rounded-full bg-[#007AFF] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
              >
                {promptLoading ? '優化中…' : '一鍵優化'}
              </button>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <section className="apple-card">
                <div className="apple-card__head">
                  <h2 className="apple-title">優化前</h2>
                </div>
                <div className="apple-card__body apple-card__body--static !pt-0">
                  <PromptEditor value={before} onChange={setBefore} height={240} />
                </div>
              </section>
              <section className="apple-card">
                <div className="apple-card__head">
                  <h2 className="apple-title">優化後</h2>
                  <span className="text-[10px] font-bold text-[#34C759]">LLM</span>
                </div>
                <div className="apple-card__body apple-card__body--static !pt-0">
                  <PromptEditor
                    value={after || '（點「一鍵優化」產生結果）'}
                    onChange={setAfter}
                    height={240}
                    readOnly={!after}
                  />
                </div>
              </section>
            </div>
            {promptError && <ErrorState kind="generic" compact message={promptError} />}
          </div>
        )}

        {tab === 'firecrawl' && (
          <div className="mx-auto max-w-3xl space-y-4">
            <section className="apple-card apple-card--pad space-y-3">
              <p className="apple-title">單頁抓取 · Scrape</p>
              <p className="text-[11px] text-[#636366]">
                有 FIRECRAWL_API_KEY 時走官方 API；否則輕量 httpx 抓取。
              </p>
              <div className="flex flex-wrap gap-2">
                <input
                  value={fcUrl}
                  onChange={(e) => setFcUrl(e.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[12px] text-[#F5F5F7]"
                />
                <button
                  type="button"
                  disabled={fcLoading}
                  onClick={() => void runFirecrawlScrape()}
                  className="rounded-full bg-[#FF9500] px-4 py-2 text-[12px] font-bold text-white disabled:opacity-50"
                >
                  Scrape
                </button>
              </div>
              {fcScrape && (
                <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                  <p className="text-[12px] font-semibold text-[#F5F5F7]">{fcScrape.title}</p>
                  <p className="mt-1 text-[10px] text-[#636366]">
                    {fcScrape.url} · {fcScrape.source}
                  </p>
                  {fcScrape.hint && (
                    <p className="mt-2 text-[10px] text-[#FF9F0A]">{fcScrape.hint}</p>
                  )}
                  {scrapeImages.length > 0 && (
                    <div className="mt-3">
                      <MediaGallery
                        items={scrapeImages.map((img) => ({
                          src: img.src,
                          caption: img.caption,
                          alt: img.caption,
                          tags: 'scrape',
                        }))}
                        layout="masonry"
                      />
                    </div>
                  )}
                  <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-[#AEAEB2]">
                    {fcScrape.markdown}
                  </pre>
                </div>
              )}
            </section>
            <section className="apple-card apple-card--pad space-y-3">
              <p className="apple-title">網頁搜尋 · Search</p>
              <div className="flex flex-wrap gap-2">
                <input
                  value={fcQuery}
                  onChange={(e) => setFcQuery(e.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[12px] text-[#F5F5F7]"
                />
                <button
                  type="button"
                  disabled={fcLoading}
                  onClick={() => void runFirecrawlSearch()}
                  className="rounded-full border border-white/10 px-4 py-2 text-[12px] font-bold text-[#F5F5F7] disabled:opacity-50"
                >
                  Search
                </button>
              </div>
              {fcSearchMarkdown && (
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-black/20 p-3 text-[11px] text-[#AEAEB2]">
                  {fcSearchMarkdown}
                </pre>
              )}
            </section>
            {fcError && <ErrorState kind="generic" compact message={fcError} />}
          </div>
        )}

        {tab === 'archify' && (
          <div className="mx-auto max-w-4xl space-y-4">
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={archLoading}
                onClick={() => void loadEvoloopArch()}
                className="rounded-full border border-white/10 px-3 py-1.5 text-[11px] font-bold text-[#AEAEB2] hover:text-[#F5F5F7]"
              >
                EvoLoop 內建圖
              </button>
            </div>
            <section className="apple-card apple-card--pad space-y-2">
              <p className="apple-title">自訂描述 → 架構 IR</p>
              <textarea
                value={archDesc}
                onChange={(e) => setArchDesc(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[12px] text-[#F5F5F7]"
              />
              <button
                type="button"
                disabled={archLoading}
                onClick={() => void runArchifyGenerate()}
                className="rounded-full bg-[#5856D6] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
              >
                {archLoading ? '生成中…' : '生成架構圖'}
              </button>
            </section>
            {archIr && <ArchifyFrame ir={archIr} fallbackIr={archIr} />}
            {archError && <ErrorState kind="generic" compact message={archError} />}
          </div>
        )}

        {tab === 'ponytail' && (
          <div className="mx-auto max-w-3xl space-y-4">
            <p className="text-[11px] text-[#636366]">
              懶惰資深工程師模式 — 審查過度工程化，停在第一個夠用的梯級。
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {(['code', 'prompt', 'diff'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setReviewKind(k)}
                  className={tabBtn(reviewKind === k)}
                >
                  {k}
                </button>
              ))}
              <button
                type="button"
                disabled={reviewLoading}
                onClick={() => void runPonytailReview()}
                className="ml-auto rounded-full bg-[#34C759] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
              >
                {reviewLoading ? '審查中…' : 'Ponytail 審查'}
              </button>
            </div>
            <PromptEditor value={reviewInput} onChange={setReviewInput} height={200} language="typescript" />
            {reviewResult && (
              <section className="apple-card apple-card--pad space-y-3">
                <p className="text-[13px] font-bold text-[#F5F5F7]">{reviewResult.review.summary}</p>
                {reviewResult.review.delete_list && reviewResult.review.delete_list.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-[#FF3B30]">可刪除</p>
                    <ul className="mt-1 list-inside list-disc text-[12px] text-[#AEAEB2]">
                      {reviewResult.review.delete_list.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {reviewResult.review.keep_list && reviewResult.review.keep_list.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-[#34C759]">必須保留</p>
                    <ul className="mt-1 list-inside list-disc text-[12px] text-[#AEAEB2]">
                      {reviewResult.review.keep_list.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {reviewResult.review.suggested_rewrite && (
                  <pre className="overflow-x-auto rounded-lg bg-black/30 p-3 text-[11px] text-[#F5F5F7]">
                    {reviewResult.review.suggested_rewrite}
                  </pre>
                )}
              </section>
            )}
            {reviewError && <ErrorState kind="generic" compact message={reviewError} />}
          </div>
        )}

        {tab === 'mcp' && (
          <div className="mx-auto max-w-2xl space-y-3">
            <p className="text-[11px] text-[#8E8E93]">
              執行期通用工具開關（OPC／記憶／爬蟲／Docker）。Minecraft 放置、填充與指令在
              「{activityNavPath('minecraft')}」，不與實驗室混用。
            </p>
            {tools.map((t) => (
              <label
                key={t.id}
                className="apple-card apple-card--tight flex cursor-pointer items-center gap-4 px-4 py-3"
              >
                <input
                  type="checkbox"
                  checked={t.enabled}
                  onChange={() =>
                    setTools((prev) =>
                      prev.map((x) => (x.id === t.id ? { ...x, enabled: !x.enabled } : x)),
                    )
                  }
                  className="h-4 w-4 accent-[#007AFF]"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-bold text-[#F5F5F7]">{t.name}</p>
                  <p className="mt-0.5 text-[11px] text-[#8E8E93]">{t.desc}</p>
                </div>
                <span
                  className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                  style={{
                    color:
                      t.risk === 'high' ? '#FF3B30' : t.risk === 'mid' ? '#FF9500' : '#34C759',
                    background:
                      t.risk === 'high'
                        ? 'rgba(255,59,48,0.12)'
                        : t.risk === 'mid'
                          ? 'rgba(255,149,0,0.12)'
                          : 'rgba(52,199,89,0.12)',
                  }}
                >
                  {t.risk}
                </span>
              </label>
            ))}
          </div>
        )}

        {tab === 'quant' && <StrategyCatalogPanel />}

        {tab === 'maps' && <StrategyMapPanel />}

        {tab === 'ab' && (
          <div className="grid gap-5 lg:grid-cols-[1fr_220px]">
            <section className="apple-card">
              <div className="apple-card__head">
                <h2 className="apple-title">記憶蒸餾 · 評分對照</h2>
              </div>
              <div className="apple-card__body apple-card__body--static apple-chart h-[280px]">
                <LcBarChart
                  height={280}
                  categories={AB_SERIES.map((row) => row.name)}
                  groups={[
                    { subCategory: '對照組 A', values: AB_SERIES.map((row) => row.a) },
                    { subCategory: '實驗組 B', values: AB_SERIES.map((row) => row.b) },
                  ]}
                />
              </div>
            </section>
            <section className="apple-card apple-card--pad flex flex-col justify-center gap-4">
              <div>
                <p className="apple-title">勝出</p>
                <p className="mt-2 text-[28px] font-bold text-[#007AFF]">變體 {winner.better}</p>
              </div>
              <div>
                <p className="text-[11px] text-[#8E8E93]">A 均分</p>
                <p className="apple-data text-[18px]">{winner.scoreA.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-[11px] text-[#8E8E93]">B 均分</p>
                <p className="apple-data text-[18px] text-[#34C759]">{winner.scoreB.toFixed(2)}</p>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
