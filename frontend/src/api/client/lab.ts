/**
 * EvoLoop 後端 API 客戶端 — 實驗室整合：Firecrawl / Prompt Optimizer / Ponytail / Archify / Quant。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import { apiUrl, readApiError } from './http';

// ═══════════════════════════════════════════════════════════
// 實驗室整合 — Firecrawl / Prompt Optimizer / Ponytail / Archify
// ═══════════════════════════════════════════════════════════

export interface FirecrawlScrapeResult {
  url: string;
  title: string;
  markdown: string;
  source: string;
  status?: number;
  hint?: string;
}

export interface FirecrawlSearchResult {
  query: string;
  results: Array<{ url: string; title: string; markdown: string }>;
  source: string;
  hint?: string;
}

export interface PromptOptimizeResult {
  original: string;
  optimized: string;
  mode: string;
  source: string;
}

export interface PonytailReviewResult {
  kind: string;
  source: string;
  review: {
    summary?: string;
    severity?: string;
    delete_list?: string[];
    keep_list?: string[];
    suggested_rewrite?: string;
  };
}

export interface ArchifyNode {
  id: string;
  label: string;
  role?: string;
  status?: string;
  lane?: string;
  detail?: string;
}

export interface ArchifyEdge {
  from: string;
  to: string;
  label?: string;
}

export interface ArchifyLane {
  id: string;
  label: string;
}

export interface ArchifyIR {
  meta?: {
    title?: string;
    type?: string;
    locale?: string;
    source?: string;
    view?: string;
    visual_preset?: string;
    inspired_by?: string;
    category?: string;
    strategy?: string;
  };
  nodes: ArchifyNode[];
  edges: ArchifyEdge[];
  lanes?: ArchifyLane[];
}

export interface StrategyMapGroup {
  id: string;
  name: string;
  total: number;
  wired: number;
  items: QuantStrategyItem[];
  architecture: ArchifyIR;
}

export interface StrategyMapCatalog {
  ok: boolean;
  inspired_by?: string;
  catalog?: string;
  engine_count?: number;
  catalog_count?: number;
  wired_count?: number;
  overview: ArchifyIR;
  data_flow: ArchifyIR;
  lifecycle: ArchifyIR;
  groups: StrategyMapGroup[];
  views?: Array<{ id: string; title: string; kind: string }>;
  disclaimer?: string;
  hint?: string;
}

export interface StrategyMapDetail {
  ok: boolean;
  item: QuantStrategyItem;
  architecture: ArchifyIR;
  workflow: ArchifyIR;
  lifecycle: ArchifyIR;
  hint?: string;
}

export interface QuantChartPoint {
  t: string;
  v: number;
}

export interface QuantPreviewChart {
  ok?: boolean;
  demo?: boolean;
  strategy?: string;
  total_return?: number;
  max_drawdown?: number;
  sharpe?: number | null;
  trades?: number;
  last_signal?: string;
  error?: string;
  note?: string;
  chart?: {
    equity: QuantChartPoint[];
    hold: QuantChartPoint[];
    close: QuantChartPoint[];
  };
}

export interface QuantStrategyPreview extends StrategyMapDetail {
  symbol?: string;
  chart?: QuantPreviewChart | null;
}

export async function labFirecrawlScrape(
  url: string,
  onlyMainContent = true,
): Promise<FirecrawlScrapeResult> {
  const resp = await fetch(apiUrl('/lab/firecrawl/scrape'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, only_main_content: onlyMainContent }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labFirecrawlSearch(query: string, limit = 5): Promise<FirecrawlSearchResult> {
  const resp = await fetch(apiUrl('/lab/firecrawl/search'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labOptimizePrompt(opts: {
  prompt: string;
  mode?: 'user' | 'system';
  goal?: string;
}): Promise<PromptOptimizeResult> {
  const resp = await fetch(apiUrl('/lab/prompt/optimize'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      prompt: opts.prompt,
      mode: opts.mode ?? 'user',
      goal: opts.goal ?? '',
    }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labPonytailReview(
  content: string,
  kind: 'code' | 'prompt' | 'diff' = 'code',
): Promise<PonytailReviewResult> {
  const resp = await fetch(apiUrl('/lab/ponytail/review'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, kind }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifyEvoloop(): Promise<ArchifyIR> {
  const resp = await fetch(apiUrl('/lab/archify/evoloop'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export interface SystemFlowEntry {
  id: string;
  title: string;
  blurb: string;
  diagram_type: string;
  legacy?: boolean;
}

export interface SystemFlowCatalog {
  ok: boolean;
  source: string;
  flows: SystemFlowEntry[];
  default_view: string;
  hint?: string;
}

export async function labArchifySystemFlows(): Promise<SystemFlowCatalog> {
  const resp = await fetch(apiUrl('/lab/archify/system-flows'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifySystemFlow(flowId: string): Promise<ArchifyIR> {
  const resp = await fetch(apiUrl(`/lab/archify/system-flows/${encodeURIComponent(flowId)}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifyGenerate(description: string): Promise<ArchifyIR> {
  const resp = await fetch(apiUrl('/lab/archify/generate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifyStrategies(): Promise<StrategyMapCatalog> {
  const resp = await fetch(apiUrl('/lab/archify/strategies'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifyStrategy(strategyId: string): Promise<StrategyMapDetail> {
  const resp = await fetch(apiUrl(`/lab/archify/strategies/${encodeURIComponent(strategyId)}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export interface ArchifyHtml {
  ok: boolean;
  html: string;
  diagram_type?: string;
  title?: string;
  engine?: string;
  source?: string;
}

export function labArchifyArtifactUrl(params: {
  view?: string;
  id?: string;
  kind?: string;
}): string {
  const query = new URLSearchParams();
  query.set('view', params.view || 'overview');
  if (params.id) query.set('id', params.id);
  if (params.kind) query.set('kind', params.kind);
  query.set('embed', '1');
  return apiUrl(`/lab/archify/artifact?${query.toString()}`);
}

export async function labArchifyHtml(params: {
  view?: string;
  id?: string;
  kind?: string;
}): Promise<ArchifyHtml> {
  const query = new URLSearchParams();
  if (params.view) query.set('view', params.view);
  if (params.id) query.set('id', params.id);
  if (params.kind) query.set('kind', params.kind);
  const resp = await fetch(apiUrl(`/lab/archify/html?${query.toString()}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifyDevRender(ir: ArchifyIR): Promise<ArchifyHtml> {
  const resp = await fetch('/__archify/render', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ir }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labArchifyRender(ir: ArchifyIR): Promise<ArchifyHtml> {
  const resp = await fetch(apiUrl('/lab/archify/render'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ir }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function labQuantPreview(
  strategy: string,
  symbol = '600519',
): Promise<QuantStrategyPreview> {
  const params = new URLSearchParams({ strategy, symbol });
  const resp = await fetch(apiUrl(`/lab/quant/preview?${params}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export interface QuantStrategyItem {
  id: string;
  name: string;
  category: string;
  category_name: string;
  status: 'wired' | 'catalog' | string;
  engine: string | null;
}

export interface QuantStrategyGroup {
  id: string;
  name: string;
  total: number;
  wired: number;
  items: QuantStrategyItem[];
}

export interface QuantStrategyCatalog {
  ok: boolean;
  engine_count: number;
  catalog_count: number;
  wired_count: number;
  matched?: number;
  groups?: QuantStrategyGroup[];
  items?: QuantStrategyItem[];
  disclaimer?: string;
  inspired_by?: string;
}

export async function labQuantStrategies(opts?: {
  category?: string;
  query?: string;
  status?: string;
}): Promise<QuantStrategyCatalog> {
  const params = new URLSearchParams();
  if (opts?.category) params.set('category', opts.category);
  if (opts?.query) params.set('query', opts.query);
  if (opts?.status) params.set('status', opts.status);
  const qs = params.toString();
  const resp = await fetch(apiUrl(`/lab/quant/strategies${qs ? `?${qs}` : ''}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export interface CapitalFlowTimelineRow {
  time: string;
  event: string;
  cash: string;
  position: string;
  margin: string;
  equity: string;
  note: string;
}

export interface CapitalFlowProfile {
  cash_buffer_pct: number;
  margin_pct: number;
  reserve_pct: number;
  position_pct: number;
  stop_loss_pct?: number;
  trailing_stop_pct?: number;
  daily_loss_limit_pct?: number;
  short_enabled?: boolean;
  intraday?: boolean;
  rebalance?: boolean;
  long_pct?: number;
  short_pct?: number;
}

export interface QuantCapitalFlow {
  ok: boolean;
  strategy: string;
  engine: string | null;
  name: string;
  symbol: string;
  initial_capital: number;
  initial_capital_fmt: string;
  profile: CapitalFlowProfile;
  waterfall_mermaid: string;
  state_machine_mermaid: string;
  timeline: CapitalFlowTimelineRow[];
  scene_hints?: { scene: string; chart: string; title: string }[];
  backtest_summary?: {
    total_return?: number;
    max_drawdown?: number;
    trades?: number;
    last_signal?: string;
  } | null;
  disclaimer?: string;
  hint?: string;
  error?: string;
}

export async function labQuantCapitalFlow(
  strategy: string,
  opts?: {
    symbol?: string;
    initialCapital?: number;
    stopLossPct?: number;
    trailingStopPct?: number;
    positionPct?: number;
    enableT1?: boolean;
  },
): Promise<QuantCapitalFlow> {
  const params = new URLSearchParams({ strategy });
  if (opts?.symbol) params.set('symbol', opts.symbol);
  if (opts?.initialCapital != null) params.set('initial_capital', String(opts.initialCapital));
  if (opts?.stopLossPct != null) params.set('stop_loss_pct', String(opts.stopLossPct));
  if (opts?.trailingStopPct != null) params.set('trailing_stop_pct', String(opts.trailingStopPct));
  if (opts?.positionPct != null) params.set('position_pct', String(opts.positionPct));
  if (opts?.enableT1) params.set('enable_t1', 'true');
  const resp = await fetch(apiUrl(`/lab/quant/capital-flow?${params}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}
