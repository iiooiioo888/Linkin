/**
 * 將監控／對話即時狀態收斂成動畫劇場可用的 live feed。
 * 劇場只視覺化真實節點、角色、費用與路由；動畫由資料增量驅動，不定時自動下一步。
 */
import type {
  AgentMonitorData,
  ChatMessage,
  CloudBilling,
  LlmOpsData,
  OptimizationMonitorData,
  RoleAgent,
  TaskProgress,
} from '../types';

export type AnimScene =
  | 'pipeline'
  | 'company'
  | 'report'
  | 'budget'
  | 'metrics'
  | 'balancer';

export interface AnimReportLine {
  id: string;
  role: string;
  line: string;
  ts?: string | null;
  accent?: string;
}

export interface AnimStageBackend {
  id: string;
  label: string;
  tier: string;
  model: string;
  weight: number;
}

export interface AnimLiveFeed {
  streamPhase?: string | null;
  taskPhase?: string | null;
  resolvedPath?: string | null;
  runningTasks: number;
  agents: RoleAgent[];
  summary?: AgentMonitorData['summary'] | null;
  optimization?: OptimizationMonitorData | null;
  billing?: CloudBilling | null;
  llmOps?: LlmOpsData | null;
  updatedAt?: string | null;
  /** 是否有真實活動（忙碌／串流／任務） */
  live: boolean;
}

/** 管線階段對照（順序敏感：較具體的規則放前面，避免子字串誤判）。 */
const PIPELINE_PHASE_RULES: Array<{ pattern: RegExp; index: number }> = [
  {
    pattern:
      /\b(improve_answer|improve|synthesize|final_review|decide_final|enforce_|save_memory|archive_state|early_stop|finalize|archive|\bdone\b|輸出|complete|output)\b/i,
    index: 5,
  },
  { pattern: /\b(reflect|reflection|反思)\b/i, index: 4 },
  { pattern: /\b(evaluate_answer|evaluate|cross_eval|評估)\b/i, index: 3 },
  {
    pattern:
      /\b(execute_review|execute|generate_initial|generate|gen|生成|draft|assigned|work_item|act_opc|run_company|company_start|company_done)\b/i,
    index: 2,
  },
  {
    pattern:
      /\b(route_by_complexity|campaign_plan|decompose|analyze_opc|diagnose_opc|decide_opc|路由|complexity|starting|resuming)\b/i,
    index: 1,
  },
  {
    pattern:
      /\b(retrieve_memories|enhance_recall(?:_context)?|enhance_opc(?:_context)?|enhance_linkin(?:_context)?|sense_opc|preprocess_opc|perceive|opc_sense|感知|sense)\b/i,
    index: 0,
  },
];

const PIPELINE_DAG_IDS = ['sense', 'route', 'gen', 'eval', 'reflect', 'out'] as const;

const TIER_WEIGHT: Record<string, number> = {
  nano: 1,
  small: 1,
  medium: 2,
  large: 3,
  xlarge: 4,
  heavy: 4,
};

export function mapPhaseToPipelineIndex(phase?: string | null): number | null {
  if (!phase) return null;
  const p = phase.trim();
  if (!p) return null;
  for (const row of PIPELINE_PHASE_RULES) {
    if (row.pattern.test(p)) return row.index;
  }
  return null;
}

/** DAG 節點 id（與 PipelineDag STAGES 對齊；公司執行與改進迴圈有獨立節點）。 */
export function mapPhaseToDagNodeId(phase?: string | null): string | null {
  if (!phase) return null;
  const p = phase.toLowerCase();
  if (/compan|orchestr|公司/.test(p)) return 'company';
  const idx = mapPhaseToPipelineIndex(phase);
  if (idx == null) return null;
  if (idx === 2 && /execute_review|campaign_plan|decompose|work_item|run_company|company_/.test(p)) {
    return 'company';
  }
  if (idx === 5 && /\bimprove/.test(p)) return 'improve';
  return PIPELINE_DAG_IDS[idx] ?? null;
}

export function pipelinePhaseLabel(phase?: string | null): string | null {
  const idx = mapPhaseToPipelineIndex(phase);
  if (idx == null) return phase?.trim() || null;
  const labels = ['感知', '路由', '生成', '評估', '反思', '輸出'];
  return labels[idx] ?? null;
}

export function tierWeight(tier?: string | null): number {
  if (!tier) return 2;
  return TIER_WEIGHT[tier.toLowerCase()] ?? 2;
}

export function stageBackends(opt?: OptimizationMonitorData | null): AnimStageBackend[] {
  const router = opt?.stage_router ?? {};
  const entries = Object.entries(router);
  if (!entries.length) {
    return [
      { id: 'generate', label: 'generate', tier: '—', model: '—', weight: 2 },
      { id: 'evaluate', label: 'evaluate', tier: '—', model: '—', weight: 2 },
      { id: 'reflect', label: 'reflect', tier: '—', model: '—', weight: 2 },
      { id: 'improve', label: 'improve', tier: '—', model: '—', weight: 2 },
    ];
  }
  return entries.map(([id, info]) => ({
    id,
    label: id,
    tier: info.tier,
    model: info.model?.split('/').pop() || info.model || '—',
    weight: tierWeight(info.tier),
  }));
}

/** 內容指紋，避免每輪輪詢因新物件參考重製動畫狀態 */
export function stageBackendsKey(backends: AnimStageBackend[]): string {
  return backends.map((b) => `${b.id}:${b.tier}:${b.model}:${b.weight}`).join('|');
}

/** 真正在跑的角色（busy／error）；waiting＋executing 殘值不視為 LIVE */
export function pickActiveAgents(agents: RoleAgent[], limit = 6): RoleAgent[] {
  return [...agents]
    .filter((a) => a.status === 'busy' || a.status === 'error')
    .sort((a, b) => (b.executing ?? 0) + (b.queue ?? 0) - ((a.executing ?? 0) + (a.queue ?? 0)))
    .slice(0, limit);
}

/** 含 waiting／開放工作項——協作扇出用，不單獨當成 LIVE */
export function pickBusyAgents(agents: RoleAgent[], limit = 6): RoleAgent[] {
  return [...agents]
    .filter(
      (a) =>
        a.status === 'busy' ||
        a.status === 'waiting' ||
        a.status === 'error' ||
        (a.work_items?.length ?? 0) > 0 ||
        (a.executing ?? 0) > 0,
    )
    .sort((a, b) => (b.executing ?? 0) + (b.queue ?? 0) - ((a.executing ?? 0) + (a.queue ?? 0)))
    .slice(0, limit);
}

export function buildReportLines(agents: RoleAgent[], limit = 8): AnimReportLine[] {
  const rows: AnimReportLine[] = [];
  for (const a of agents) {
    for (const ev of a.events ?? []) {
      rows.push({
        id: `${a.id}-${ev.ts}-${ev.event}-${ev.item_id ?? ''}`,
        role: a.name,
        line: ev.title || ev.event.replace(/_/g, ' '),
        ts: ev.ts,
        accent: ev.event.includes('error') ? '#f87171' : undefined,
      });
    }
    if (a.current_item) {
      rows.push({
        id: `${a.id}-current`,
        role: a.name,
        line: `${a.current_item.title} · ${a.current_item.status}`,
        ts: a.current_item.updated_at,
      });
    }
  }
  rows.sort((x, y) => (y.ts || '').localeCompare(x.ts || ''));
  const dedup = rows.filter((r, i, arr) => arr.findIndex((x) => x.id === r.id) === i);
  return dedup.slice(0, limit);
}

export function budgetPct(summary?: AgentMonitorData['summary'] | null): {
  apiPct: number;
  cloudPct: number;
  apiUsd: number;
  cloudUsd: number;
  totalUsd: number;
} {
  const apiUsd = summary?.total_api_cost_usd ?? 0;
  const cloudUsd =
    summary?.total_cloud_cost_usd ??
    (summary?.total_docker_cost_usd ?? 0) + (summary?.total_aliyun_cost_usd ?? 0);
  const totalUsd = summary?.total_cost_usd ?? apiUsd + cloudUsd;
  const base = Math.max(totalUsd, 0.0001);
  return {
    apiUsd,
    cloudUsd,
    totalUsd,
    apiPct: Math.min(100, Math.round((apiUsd / base) * 100)),
    cloudPct: Math.min(100, Math.round((cloudUsd / base) * 100)),
  };
}

function activeTaskFromMessages(messages: ChatMessage[]): TaskProgress | null {
  const streaming = messages.find((m) => m.streaming && m.taskState);
  if (streaming?.taskState) return streaming.taskState;
  const running = [...messages]
    .reverse()
    .find(
      (m) =>
        m.taskState &&
        (m.taskState.status === 'running' || m.taskState.status === 'pending'),
    );
  return running?.taskState ?? null;
}

function latestPhaseFromMessages(messages: ChatMessage[]): {
  streamPhase: string | null;
  taskPhase: string | null;
} {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.streamPhase) return { streamPhase: m.streamPhase, taskPhase: m.taskState?.phase ?? null };
    if (m.taskState?.phase) return { streamPhase: null, taskPhase: m.taskState.phase };
  }
  return { streamPhase: null, taskPhase: null };
}

export function buildAnimLiveFeed(opts: {
  agents?: AgentMonitorData | null;
  optimization?: OptimizationMonitorData | null;
  billing?: CloudBilling | null;
  llmOps?: LlmOpsData | null;
  messages?: ChatMessage[];
  updatedAt?: string | null;
}): AnimLiveFeed {
  const messages = opts.messages ?? [];
  const task = activeTaskFromMessages(messages);
  const streamingMsg = messages.find((m) => m.streaming);
  const latestPhase = latestPhaseFromMessages(messages);
  const roster = opts.agents?.agents ?? [];
  const active = pickActiveAgents(roster);
  const runningTasks = messages.filter(
    (m) => m.taskState?.status === 'running' || m.taskState?.status === 'pending',
  ).length;
  /** 僅串流／進行中任務／真正忙碌角色 → LIVE；waiting 佇列不算自動演示 */
  const live = Boolean(
    streamingMsg ||
      runningTasks > 0 ||
      active.length > 0 ||
      (opts.agents?.summary?.roles_busy ?? 0) > 0 ||
      (opts.agents?.summary?.running_company_tasks ?? 0) > 0,
  );

  return {
    streamPhase: streamingMsg?.streamPhase ?? latestPhase.streamPhase,
    taskPhase: task?.phase ?? latestPhase.taskPhase,
    resolvedPath: task?.resolved_path || null,
    runningTasks,
    agents: roster,
    summary: opts.agents?.summary ?? null,
    optimization: opts.optimization ?? null,
    billing: opts.billing ?? null,
    llmOps: opts.llmOps ?? null,
    updatedAt: opts.updatedAt ?? null,
    live,
  };
}
