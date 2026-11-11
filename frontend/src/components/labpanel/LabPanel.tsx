/**
 * 實驗室面板 — Firecrawl · Prompt Optimizer · Archify · Ponytail · 策略庫 · 策略圖 · MCP · A/B。
 *
 * 第六輪重構：JSX 與狀態已拆至 ./labpanel/ 子元件；本檔保留全部 state 與載入／操作邏輯，
 * 分頁內容以 props 傳入對應子元件（hooks 呼叫順序與資料流不變）。
 */

import { useCallback, useEffect, useState } from 'react';
import type {
  ArchifyIR,
  FirecrawlScrapeResult,
  PonytailReviewResult,
  SystemFlowCatalog,
  SystemFlowEntry,
} from '../../api/client';
import {
  fetchLabPrefs,
  labArchifyGenerate,
  labArchifySystemFlows,
  labFirecrawlScrape,
  labFirecrawlSearch,
  labOptimizePrompt,
  labPonytailReview,
  saveLabPrefs,
} from '../../api/client';
import { isLabLink, LAB_TABS, labGroupForTab, labSectionForTab, type LabSubTab } from '../../lib/labTabs';
import EphemeralContainerPanel from '../EphemeralContainerPanel';
import StrategyCatalogPanel from '../StrategyCatalogPanel';
import StrategyMapPanel from '../StrategyMapPanel';
import { AbTab } from './AbTab';
import { ArchifyTab } from './ArchifyTab';
import { DEMO_BEFORE, MCP_TOOLS, tabBtn } from './constants';
import { FirecrawlTab } from './FirecrawlTab';
import { McpTab } from './McpTab';
import { PonytailTab } from './PonytailTab';
import { PromptTab } from './PromptTab';
import { UpstreamLink } from './UpstreamLink';

interface LabPanelProps {
  activeTab: LabSubTab;
  onTabChange: (tab: LabSubTab) => void;
}

export default function LabPanel({ activeTab, onTabChange }: LabPanelProps) {
  const tab = activeTab;
  const tabMeta = LAB_TABS.find((t) => t.key === tab);
  const activeGroup = labGroupForTab(tab);
  const activeSection = labSectionForTab(tab);
  const chipTitle = activeSection?.label || activeGroup?.label;
  const chipItems = activeSection?.items ?? [];

  // Prompt Optimizer
  const [before, setBefore] = useState(DEMO_BEFORE);
  const [after, setAfter] = useState('');
  const [promptMode, setPromptMode] = useState<'user' | 'system'>('user');
  const [promptGoal, setPromptGoal] = useState('更簡潔、可執行');
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptError, setPromptError] = useState<string | null>(null);

  // Firecrawl
  const [fcUrl, setFcUrl] = useState('https://docs.firecrawl.dev');
  const [fcQuery, setFcQuery] = useState('Linkin AI agent');
  const [fcScrape, setFcScrape] = useState<FirecrawlScrapeResult | null>(null);
  const [fcSearchMarkdown, setFcSearchMarkdown] = useState('');
  const [fcLoading, setFcLoading] = useState(false);
  const [fcError, setFcError] = useState<string | null>(null);

  // Archify
  const [archFlows, setArchFlows] = useState<SystemFlowEntry[]>([]);
  const [archFlowView, setArchFlowView] = useState('langgraph');
  const [archCustomIr, setArchCustomIr] = useState<ArchifyIR | null>(null);
  const [archDesc, setArchDesc] = useState('Browser -> FastAPI -> LangGraph -> LiteLLM -> Redis/Chroma');
  const [archLoading, setArchLoading] = useState(false);
  const [archCatalogLoading, setArchCatalogLoading] = useState(false);
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
  const [toolStatus, setToolStatus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchLabPrefs()
      .then((prefs) => {
        if (cancelled) return;
        setTools((prev) =>
          prev.map((tool) =>
            Object.prototype.hasOwnProperty.call(prefs.mcp_tools, tool.id)
              ? { ...tool, enabled: Boolean(prefs.mcp_tools[tool.id]) }
              : tool,
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setToolStatus('讀取此帳號的實驗室開關失敗');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const persistTools = (next: typeof MCP_TOOLS) => {
    setTools(next);
    setToolStatus('儲存中…');
    const payload = Object.fromEntries(next.map((tool) => [tool.id, tool.enabled]));
    void saveLabPrefs(payload)
      .then(() => setToolStatus('已儲存到此帳號'))
      .catch((err: Error) => setToolStatus(err.message));
  };

  const loadArchFlows = useCallback(async () => {
    setArchCatalogLoading(true);
    setArchError(null);
    try {
      const catalog: SystemFlowCatalog = await labArchifySystemFlows();
      setArchFlows(catalog.flows ?? []);
      if (catalog.default_view) setArchFlowView(catalog.default_view);
    } catch (err) {
      setArchError((err as Error).message);
    } finally {
      setArchCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'archify' && archFlows.length === 0 && !archCatalogLoading) {
      void loadArchFlows();
    }
  }, [tab, archFlows.length, archCatalogLoading, loadArchFlows]);

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
      setArchCustomIr(await labArchifyGenerate(archDesc));
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
        {chipTitle && chipItems.length > 0 && (
          <div className="mx-auto mb-5 max-w-5xl md:hidden">
            <p className="mb-2 text-[10px] font-semibold tracking-wide text-[var(--console-faint)]">
              {chipTitle}
            </p>
            <div className="flex flex-wrap gap-2">
              {chipItems.map((item) =>
                isLabLink(item) ? (
                  <a
                    key={item.key}
                    href={item.href}
                    className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-left no-underline hover:bg-white/[0.04]"
                  >
                    <span className="block text-[12px] font-bold text-[var(--console-ink)]">{item.label}</span>
                    {item.hint ? (
                      <span className="mt-0.5 block text-[10px] text-[var(--console-sub)]">{item.hint}</span>
                    ) : null}
                  </a>
                ) : (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onTabChange(item.key)}
                    className={`rounded-xl border px-3 py-2 text-left transition-colors ${
                      tab === item.key
                        ? 'border-[color-mix(in_srgb,var(--console-accent)_50%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)]'
                        : 'border-white/[0.06] bg-white/[0.02] hover:bg-white/[0.04]'
                    }`}
                  >
                    <span className="block text-[12px] font-bold text-[var(--console-ink)]">{item.label}</span>
                    {item.upstream && (
                      <span className="mt-0.5 block text-[10px] text-[var(--console-sub)]">{item.upstream.name}</span>
                    )}
                  </button>
                ),
              )}
            </div>
          </div>
        )}

        {tabMeta?.upstream && (
          <div className="mx-auto mb-4 flex max-w-5xl items-center gap-2">
            <UpstreamLink name={tabMeta.upstream.name} url={tabMeta.upstream.url} />
            <span className="text-[10px] text-[var(--console-faint)]">
              {tab === 'quant' ? '角色 tool_call 引用' : tab === 'maps' ? 'Archify 可視化 · 角色可引用' : '後端 API · LLM 經 call_llm'}
            </span>
          </div>
        )}

        {tab === 'prompt' && (
          <PromptTab
            before={before}
            setBefore={setBefore}
            after={after}
            setAfter={setAfter}
            promptMode={promptMode}
            setPromptMode={setPromptMode}
            promptGoal={promptGoal}
            setPromptGoal={setPromptGoal}
            promptLoading={promptLoading}
            promptError={promptError}
            runPromptOptimize={runPromptOptimize}
          />
        )}

        {tab === 'firecrawl' && (
          <FirecrawlTab
            fcUrl={fcUrl}
            setFcUrl={setFcUrl}
            fcQuery={fcQuery}
            setFcQuery={setFcQuery}
            fcScrape={fcScrape}
            fcSearchMarkdown={fcSearchMarkdown}
            fcLoading={fcLoading}
            fcError={fcError}
            runFirecrawlScrape={runFirecrawlScrape}
            runFirecrawlSearch={runFirecrawlSearch}
          />
        )}

        {tab === 'archify' && (
          <ArchifyTab
            archFlows={archFlows}
            archFlowView={archFlowView}
            setArchFlowView={setArchFlowView}
            archCustomIr={archCustomIr}
            setArchCustomIr={setArchCustomIr}
            archDesc={archDesc}
            setArchDesc={setArchDesc}
            archLoading={archLoading}
            archCatalogLoading={archCatalogLoading}
            archError={archError}
            runArchifyGenerate={runArchifyGenerate}
          />
        )}

        {tab === 'ponytail' && (
          <PonytailTab
            reviewInput={reviewInput}
            setReviewInput={setReviewInput}
            reviewKind={reviewKind}
            setReviewKind={setReviewKind}
            reviewResult={reviewResult}
            reviewLoading={reviewLoading}
            reviewError={reviewError}
            runPonytailReview={runPonytailReview}
          />
        )}

        {tab === 'mcp' && <McpTab tools={tools} toolStatus={toolStatus} persistTools={persistTools} />}

        {tab === 'runner' && <EphemeralContainerPanel />}

        {tab === 'quant' && <StrategyCatalogPanel />}

        {tab === 'maps' && <StrategyMapPanel />}

        {tab === 'ab' && <AbTab />}
      </div>
    </div>
  );
}
