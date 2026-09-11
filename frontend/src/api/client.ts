/**
 * EvoLoop 後端 API 客戶端。
 *
 * 適配遠程版後端：僅提供 POST /chat（同步回傳完整回答）
 * 與 GET /health；串流、回饋、歷史端點待後端支援後啟用。
 *
 * 開發環境透過 Vite 代理（/api → http://localhost:8000）；
 * 生產環境可設定 VITE_API_URL 環境變數指向後端位址。
 */

import type { AgentMonitorData, AgentMonitorPrefs, AliyunBilling, ApiRoutePublic, BattlePlanState, BillingLedgerEntry, BillingSnapshot, BillingUsageEvent, CheckpointSummary, CloudAlertsData, CloudBilling, CloudEventsData, CloudMonitoring, DashboardData, DockerActionResult, DockerBudget, DockerStatus, GrillUserState, HubMonitorData, LlmOpsData, L0Snapshot, OpcMonitorData, OptimizationMonitorData, RahoSnapshot, RoleAgent, SeatFeedQuery, SeatIOFeed, SeatIORecord, TaskOptions, TaskProgress, TraceEntry, TraceSummary } from '../types';
import { appendGateQuery } from '../lib/auth';

const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export interface ChatOptions {
  /** 統一模式執行策略：auto（自動判斷）/ simple（單次生成）/ company（公司運行時） */
  executionStrategy?: 'auto' | 'simple' | 'company';
  /** 公司組織模板（execution_strategy 為 company 時生效） */
  companyTemplate?: string;
  /** 多輪對話歷史：[{"role": "user"|"assistant", "content": "..."}] */
  history?: Array<{ role: string; content: string }>;
  /** 需求審計官核發的戰術指令 */
  semantic_lock?: Record<string, unknown>;
}

export interface ChatBillingFootnote {
  credits_deducted?: number;
  pricing_version?: number;
  cache_savings_credits?: number;
  vendor_id?: string;
  interrupted?: boolean;
  interrupt_reason?: string;
}

export interface ChatResult {
  session_id: string;
  answer: string;
  score: number | null;
  iteration: number;
  billing?: ChatBillingFootnote;
}

/** SSE 串流事件回調 */
export interface StreamCallbacks {
  onPhase?: (phase: string) => void;
  onToken?: (token: string) => void;
  onAnswer?: (answer: string) => void;
  onEvaluation?: (score: number | null, iteration: number, multiDim?: import('../types').MultiDimEvaluation) => void;
  onDone?: (answer: string, score: number | null, iteration: number, thinking?: string, billing?: ChatBillingFootnote) => void;
  onBilling?: (billing: ChatBillingFootnote) => void;
  onError?: (error: string) => void;
}

async function parseBillingError(resp: Response): Promise<string> {
  const body = await resp.json().catch(() => ({})) as { detail?: string; code?: string };
  if (resp.status === 402) {
    return body.detail || '靈境積分不足，請充值或升級方案後再試';
  }
  if (resp.status === 403 && body.detail?.includes('轉贈')) {
    return '積分不可轉贈、轉移或提現';
  }
  return body.detail || `請求失敗（HTTP ${resp.status}）`;
}

/**
 * 送出聊天並以 SSE 串流接收回答（打字機效果）。
 *
 * 統一模式：複雜任務（公司運行時路徑）會自動降級為同步回傳。
 * 回傳 AbortController 供取消請求。
 */
export function sendChatStream(
  query: string,
  sessionId: string,
  callbacks: StreamCallbacks,
  history?: Array<{ role: string; content: string }>,
  extra?: { semantic_lock?: Record<string, unknown> },
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(apiUrl('/chat/stream'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          session_id: sessionId,
          history: history ?? [],
          semantic_lock: extra?.semantic_lock ?? {},
        }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        callbacks.onError?.(await parseBillingError(resp));
        return;
      }
      if (!resp.body) {
        callbacks.onError?.('串流回應為空');
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件（以 \n\n 分隔）
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const eventMatch = part.match(/^event:\s*(.+)$/m);
          const dataMatch = part.match(/^data:\s*(.+)$/m);
          if (!eventMatch || !dataMatch) continue;

          const eventType = eventMatch[1].trim();
          let data: Record<string, unknown>;
          try {
            data = JSON.parse(dataMatch[1]);
          } catch {
            continue;
          }

          switch (eventType) {
            case 'phase':
              callbacks.onPhase?.(String(data.phase ?? ''));
              break;
            case 'token':
              callbacks.onToken?.(String(data.token ?? ''));
              break;
            case 'answer':
              callbacks.onAnswer?.(String(data.answer ?? ''));
              break;
            case 'evaluation':
              callbacks.onEvaluation?.(
                (data.score as number) ?? null,
                (data.iteration as number) ?? 0,
                (data.multi_dim as import('../types').MultiDimEvaluation) ?? undefined,
              );
              break;
            case 'billing':
              callbacks.onBilling?.(data as ChatBillingFootnote);
              break;
            case 'done':
              callbacks.onDone?.(
                String(data.answer ?? ''),
                (data.score as number) ?? null,
                (data.iteration as number) ?? 0,
                String(data.thinking ?? ''),
                (data.billing as ChatBillingFootnote) ?? undefined,
              );
              break;
            case 'error':
              callbacks.onError?.(String(data.error ?? '未知錯誤'));
              break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.((err as Error).message || '網路連線失敗');
      }
    }
  })();

  return controller;
}

/** 送出聊天並取得完整回答（統一模式）。 */
export async function sendChat(
  query: string,
  sessionId: string,
  options: ChatOptions = {},
): Promise<ChatResult> {
  let resp: Response;
  try {
    resp = await fetch(apiUrl('/chat'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        session_id: sessionId,
        execution_strategy: options.executionStrategy ?? 'auto',
        company_template: options.companyTemplate ?? 'quick_task',
        history: options.history ?? [],
      }),
    });
  } catch {
    throw new Error('網路連線失敗，請檢查後端服務是否啟動');
  }

  if (!resp.ok) {
    throw new Error(await parseBillingError(resp));
  }
  const data = await resp.json();
  return {
    session_id: data.session_id ?? sessionId,
    answer: data.answer ?? '',
    score: data.score ?? null,
    iteration: data.iteration ?? 0,
    billing: data.billing as ChatBillingFootnote | undefined,
  };
}

/** 送出 👍/👎 回饋（盡力而為：後端尚未提供 /feedback 時靜默忽略）。 */
export async function sendFeedback(sessionId: string, rating: 1 | 2): Promise<void> {
  try {
    await fetch(apiUrl('/feedback'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, rating }),
    });
  } catch {
    // 後端未提供回饋端點時不影響體驗
  }
}

// ==================== LLM 配置 ====================

export interface LlmConfig {
  configured: boolean;
  api_key: string; // 脱敏後的金鑰
  api_base: string;
  model: string;
  provider_kind?: string;
  provider_label?: string;
  lock_message?: string;
  allowed_models?: string[];
  catalog?: Array<{ id: string; name: string; owned_by: string }>;
  catalog_source?: string;
  catalog_fetched_at?: string;
  catalog_error?: string;
  route_strategy?: string;
  default_route_id?: string;
  api_routes?: ApiRoutePublic[];
  models_by_provider?: LlmOpsData['models_by_provider'];
  route_strategies?: LlmOpsData['route_strategies'];
  provider_presets?: LlmOpsData['provider_presets'];
  ops?: LlmOpsData['ops'];
}

export interface ApiRouterState {
  route_strategy: string;
  default_route_id: string;
  strategies: Array<{ id: string; label: string }>;
  presets: Array<{ id: string; name: string; api_base: string; model: string; label: string }>;
  api_routes: ApiRoutePublic[];
  allowed_models: string[];
  models_by_provider: NonNullable<LlmOpsData['models_by_provider']>;
}

/** 取得当前 LLM 配置狀態。 */
export async function fetchConfig(): Promise<LlmConfig> {
  const resp = await fetch(apiUrl('/config'));
  if (!resp.ok) throw new Error(`讀取配置失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 儲存 LLM 配置（api_key 傳空字串表示不變更可另處理）。 */
export async function saveConfig(config: {
  api_key?: string;
  api_base?: string;
  model?: string;
}): Promise<LlmConfig> {
  const resp = await fetch(apiUrl('/config'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!resp.ok) throw new Error(`儲存配置失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchLlmOps(): Promise<LlmOpsData> {
  const resp = await fetch(apiUrl('/monitor/llm-ops'));
  if (!resp.ok) throw new Error(`讀取 LLM 運維失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchOptimizationMonitor(): Promise<OptimizationMonitorData> {
  const resp = await fetch(apiUrl('/monitor/optimization'));
  if (!resp.ok) throw new Error(`讀取優化監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function refreshLlmModels(): Promise<LlmOpsData> {
  const resp = await fetch(apiUrl('/config/models/refresh'), { method: 'POST' });
  if (!resp.ok) throw new Error(`刷新模型目錄失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function updateLlmOpsPrefs(refreshIntervalSec: number): Promise<LlmOpsData> {
  const resp = await fetch(apiUrl('/config/ops'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_interval_sec: refreshIntervalSec }),
  });
  if (!resp.ok) throw new Error(`更新運維間隔失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 以当前配置測試 LLM 連線。 */
export async function testConfig(): Promise<{ ok: boolean; reply?: string; error?: string }> {
  const resp = await fetch(apiUrl('/config/test'), { method: 'POST' });
  if (!resp.ok) throw new Error(`測試請求失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchApiRoutes(): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl('/config/routes'));
  if (!resp.ok) throw new Error(`讀取 API 路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function upsertApiRoute(payload: {
  id?: string;
  name?: string;
  provider?: string;
  api_key?: string;
  api_base?: string;
  model?: string;
  allowed_models?: string[];
  weight?: number;
  enabled?: boolean;
  fallback?: boolean;
  is_default?: boolean;
  models_locked?: boolean;
  keep_api_key?: boolean;
  provider_routing?: Record<string, unknown> | null;
}): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl('/config/routes'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`儲存 API 路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function deleteApiRoute(routeId: string): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl(`/config/routes/${encodeURIComponent(routeId)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(`刪除 API 路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function refreshApiRoute(routeId: string): Promise<ApiRoutePublic> {
  const resp = await fetch(apiUrl(`/config/routes/${encodeURIComponent(routeId)}/refresh`), { method: 'POST' });
  if (!resp.ok) throw new Error(`刷新路由目錄失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function testApiRoute(routeId: string): Promise<{ ok: boolean; reply?: string; error?: string; route_id?: string }> {
  const resp = await fetch(apiUrl(`/config/routes/${encodeURIComponent(routeId)}/test`), { method: 'POST' });
  if (!resp.ok) throw new Error(`測試路由失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function updateRouteStrategy(routeStrategy: string, defaultRouteId?: string): Promise<ApiRouterState> {
  const resp = await fetch(apiUrl('/config/strategy'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ route_strategy: routeStrategy, default_route_id: defaultRouteId }),
  });
  if (!resp.ok) throw new Error(`更新路由策略失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：需求審計官開場（聊天閘門，簡單寒暄可跳過）。 */
export async function startUserGrill(
  query: string,
  executionStrategy: 'auto' | 'simple' | 'company' = 'auto',
): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/raho/grill/start'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, execution_strategy: executionStrategy }),
  });
  if (!resp.ok) throw new Error(`需求審計啟動失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：回答審計追問。forceLock 視同過度授權，不會繞過五維門檻。 */
export async function turnUserGrill(
  sessionId: string,
  answer: string,
  forceLock = false,
): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/raho/grill/turn'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer, force_lock: forceLock }),
  });
  if (!resp.ok) throw new Error(`需求審計回合失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 強制前置閘門：一律開審。 */
export async function startAuditor(query: string): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/auditor/start'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) throw new Error(`需求審計官啟動失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 強制前置閘門：繼續追問。 */
export async function turnAuditor(
  sessionId: string,
  answer: string,
  forceLock = false,
): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/auditor/turn'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer, force_lock: forceLock }),
  });
  if (!resp.ok) throw new Error(`需求審計官回合失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 強制前置閘門：SSE 回傳本輪拷問、五維評分與終態門票。 */
export async function streamAuditor(params: {
  query?: string;
  sessionId?: string;
  answer?: string;
  forceLock?: boolean;
}): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/auditor/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: params.query ?? '',
      session_id: params.sessionId ?? '',
      answer: params.answer ?? '',
      force_lock: params.forceLock ?? false,
    }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`需求審計官串流失敗（HTTP ${resp.status}）`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: GrillUserState | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const eventMatch = part.match(/^event:\s*(.+)$/m);
      const dataMatch = part.match(/^data:\s*(.+)$/m);
      if (!eventMatch || !dataMatch) continue;
      const eventType = eventMatch[1].trim();
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataMatch[1]);
      } catch {
        continue;
      }
      if (eventType === 'error') {
        throw new Error(String(data.error || '需求審計官串流失敗'));
      }
      if (eventType === 'done') {
        result = data as unknown as GrillUserState;
      }
    }
  }
  if (!result) throw new Error('需求審計官串流未回傳結果');
  return result;
}

/** RAHO：L0 環境與記憶核心。 */
export async function fetchL0Kernel(query = '', nodeId = ''): Promise<L0Snapshot> {
  const params = new URLSearchParams();
  if (query) params.set('query', query);
  if (nodeId) params.set('node_id', nodeId);
  const q = params.toString() ? `?${params.toString()}` : '';
  const resp = await fetch(apiUrl(`/raho/l0${q}`));
  if (!resp.ok) throw new Error(`讀取 L0 核心失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：質詢樹與決策阻塞點。 */
export async function fetchRahoTree(runId?: string): Promise<RahoSnapshot> {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
  const resp = await fetch(apiUrl(`/raho/tree${q}`));
  if (!resp.ok) throw new Error(`讀取質詢樹失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：L3 戰術指揮官拆解 L4 門票。 */
export async function planBattle(
  ticket?: Record<string, unknown> | null,
  lockedBrief = '',
): Promise<BattlePlanState> {
  const resp = await fetch(apiUrl('/raho/commander/plan'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket: ticket ?? undefined, locked_brief: lockedBrief, use_llm: false }),
  });
  if (!resp.ok) throw new Error(`戰術拆解失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：用戶裁決熱馬桶圈。 */
export async function decideRaho(decisionId: string, choice: string, note = ''): Promise<RahoSnapshot> {
  const resp = await fetch(apiUrl('/raho/decide'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision_id: decisionId, choice, note }),
  });
  if (!resp.ok) {
    let detail = `裁決失敗（HTTP ${resp.status}）`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json();
}

// ==================== 任務介面 ====================

/** 建立後台任務（統一模式），回傳 task_id。 */
export async function createTask(
  query: string,
  executionStrategy: 'auto' | 'simple' | 'company' = 'auto',
  companyTemplate: string = 'quick_task',
  options?: TaskOptions,
): Promise<{ task_id: string; strategy: string }> {
  let resp: Response;
  try {
    resp = await fetch(apiUrl('/tasks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        execution_strategy: executionStrategy,
        company_template: companyTemplate,
        options: options ?? {},
      }),
    });
  } catch {
    throw new Error('網路連線失敗，請檢查後端服務是否啟動');
  }
  if (!resp.ok) throw new Error(await parseBillingError(resp));
  return resp.json();
}

/** 斷點續跑：從檢查點恢復任務執行。 */
export async function resumeTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/resume`), {
    method: 'POST',
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? `恢復失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

/** 獲取任務的思考過程記錄（分頁 + 可篩選；event/role 逗號分隔多值）。 */
export async function fetchTaskTrace(
  taskId: string,
  limit: number = 100,
  offset: number = 0,
  filters?: { event?: string; role?: string; itemId?: string; withCounts?: boolean },
): Promise<{
  task_id: string;
  offset: number;
  limit: number;
  events: TraceEntry[];
  event_counts?: Record<string, number>;
}> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (filters?.event) params.set('event', filters.event);
  if (filters?.role) params.set('role', filters.role);
  if (filters?.itemId) params.set('item_id', filters.itemId);
  if (filters?.withCounts) params.set('with_counts', 'true');
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/trace?${params}`));
  if (!resp.ok) throw new Error(`讀取軌跡失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取任務的檢查點信息。 */
export async function fetchTaskCheckpoint(taskId: string): Promise<{
  task_id: string;
  exists: boolean;
  checkpoint?: Record<string, unknown>;
}> {
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/checkpoint`));
  if (!resp.ok) throw new Error(`讀取檢查點失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 列出所有思考過程軌跡檔案摘要。 */
export async function fetchTraces(limit: number = 80): Promise<{ traces: TraceSummary[] }> {
  const resp = await fetch(apiUrl(`/traces?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取軌跡列表失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 列出所有可恢復的檢查點。 */
export async function fetchCheckpoints(): Promise<{ checkpoints: CheckpointSummary[] }> {
  const resp = await fetch(apiUrl('/checkpoints'));
  if (!resp.ok) throw new Error(`讀取檢查點列表失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 查詢任務進度。eventsLimit=0 表示向後端索取全部事件（預設 50）。 */
export async function fetchTask(taskId: string, eventsLimit?: number): Promise<TaskProgress> {
  const q = eventsLimit === undefined ? '' : `?events_limit=${eventsLimit}`;
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}${q}`));
  if (!resp.ok) throw new Error(`查詢任務失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 席位投遞餵給（公司模式監察頁資料源）。 */
export async function fetchSeatFeed(params: SeatFeedQuery = {}): Promise<SeatIOFeed> {
  const q = new URLSearchParams();
  if (params.task_id) q.set('task_id', params.task_id);
  if (params.run_id) q.set('run_id', params.run_id);
  if (params.role) q.set('role', params.role);
  if (params.layer !== undefined) q.set('layer', String(params.layer));
  if (params.item_id) q.set('item_id', params.item_id);
  if (params.kind) q.set('kind', params.kind);
  q.set('limit', String(params.limit ?? 120));
  if (params.full) q.set('full', 'true');
  const resp = await fetch(apiUrl(`/monitor/raho/feed?${q.toString()}`));
  if (!resp.ok) throw new Error(`讀取席位投遞失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 單次席位投遞全文（系統提示詞／prompt／回應／來源分解）。 */
export async function fetchSeatDetail(ioId: string): Promise<SeatIORecord> {
  const resp = await fetch(apiUrl(`/monitor/raho/seat/${encodeURIComponent(ioId)}`));
  if (!resp.ok) throw new Error(`讀取投遞全文失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 請求取消執行中的任務。 */
export async function cancelTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/cancel`), {
    method: 'POST',
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? `取消失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

// ==================== 任務 WebSocket 實時推送 ====================

/** WebSocket 事件消息格式。 */
export interface TaskWsMessage {
  task_id: string;
  event: string;
  data: Record<string, unknown>;
}

/** 取得 WebSocket URL（適配 Vite 代理與生產環境）。 */
function wsUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL ?? '/api';
  let url: string;
  // 生產環境或完整 URL：轉換 http(s) → ws(s)
  if (base.startsWith('http')) {
    url = base.replace(/^http/, 'ws') + path;
  } else {
    // 開發環境 Vite 代理：使用當前 host
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    url = `${proto}://${window.location.host}${base}${path}`;
  }
  return appendGateQuery(url);
}

/**
 * 任務 WebSocket 客戶端。
 *
 * 連接後自動接收任務進度推送，支援：
 * - onMessage: 事件回調
 * - 自動重連（可選）
 * - 心跳保持連接
 */
export class TaskWebSocket {
  private ws: WebSocket | null = null;
  private taskId: string;
  private onMessage: (msg: TaskWsMessage) => void;
  private onClose?: () => void;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private shouldReconnect = true;

  constructor(
    taskId: string,
    onMessage: (msg: TaskWsMessage) => void,
    onClose?: () => void,
  ) {
    this.taskId = taskId;
    this.onMessage = onMessage;
    this.onClose = onClose;
  }

  /** 建立 WebSocket 連接。 */
  connect(): void {
    try {
      this.ws = new WebSocket(wsUrl(`/tasks/${encodeURIComponent(this.taskId)}/ws`));
    } catch {
      // WebSocket 不可用時降級為輪詢
      this.onClose?.();
      return;
    }

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as TaskWsMessage;
        this.onMessage(msg);
      } catch {
        // 忽略解析失敗的消息
      }
    };

    this.ws.onclose = () => {
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
      } else {
        this.onClose?.();
      }
    };

    this.ws.onerror = () => {
      // 錯誤時關閉連接（觸發重連或降級）
      this.ws?.close();
    };
  }

  /** 發送心跳。 */
  ping(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping');
    }
  }

  /** 關閉連接（不再重連）。 */
  close(): void {
    this.shouldReconnect = false;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('close');
    }
    this.ws?.close();
  }

  /** 連接是否已建立。 */
  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

/** 監控中心 Hub WebSocket：週期推送彙總快照。 */
export class MonitorHubWebSocket {
  private ws: WebSocket | null = null;
  private onSnapshot: (snap: Record<string, unknown>) => void;
  private onClose?: () => void;
  private heartbeat: ReturnType<typeof setInterval> | null = null;

  constructor(
    onSnapshot: (snap: Record<string, unknown>) => void,
    onClose?: () => void,
  ) {
    this.onSnapshot = onSnapshot;
    this.onClose = onClose;
  }

  connect(): void {
    try {
      this.ws = new WebSocket(wsUrl('/monitor/ws'));
    } catch {
      this.onClose?.();
      return;
    }

    this.ws.onopen = () => {
      this.heartbeat = setInterval(() => this.ping(), 15000);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as {
          event?: string;
          data?: Record<string, unknown>;
        };
        if (msg.event === 'snapshot' && msg.data) {
          this.onSnapshot(msg.data);
        } else if (msg.event !== 'pong') {
          this.onSnapshot(msg as Record<string, unknown>);
        }
      } catch {
        // ignore
      }
    };

    this.ws.onclose = () => {
      if (this.heartbeat) {
        clearInterval(this.heartbeat);
        this.heartbeat = null;
      }
      this.onClose?.();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  ping(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping');
    }
  }

  close(): void {
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('close');
    }
    this.ws?.close();
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

/** 一次性拉取監控彙總快照（REST 降級）。 */
export async function fetchMonitorHubSnapshot(): Promise<Record<string, unknown>> {
  const resp = await fetch(apiUrl('/monitor/hub-snapshot'));
  if (!resp.ok) throw new Error(`監控快照失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== 記憶庫管理 ====================

/** 記憶項目 */
export interface MemoryItem {
  id: string;
  text: string;
  metadata: Record<string, unknown>;
}

/** 列出記憶庫中的記憶（分頁）。 */
export async function fetchMemories(limit: number = 100, offset: number = 0): Promise<{
  total: number;
  offset: number;
  limit: number;
  memories: MemoryItem[];
  error?: string;
}> {
  const resp = await fetch(apiUrl(`/memories?limit=${limit}&offset=${offset}`));
  if (!resp.ok) throw new Error(`讀取記憶庫失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 刪除單條記憶。 */
export async function deleteMemory(memoryId: string): Promise<{ deleted: boolean; id: string }> {
  const resp = await fetch(apiUrl(`/memories/${encodeURIComponent(memoryId)}`), {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(`刪除記憶失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 清理過期或低品質記憶。 */
export async function cleanupMemories(
  maxAgeDays: number = 30,
  minScore?: number,
): Promise<{ deleted_count: number }> {
  const params = new URLSearchParams({ max_age_days: String(maxAgeDays) });
  if (minScore != null) params.set('min_score', String(minScore));
  const resp = await fetch(apiUrl(`/memories/cleanup?${params.toString()}`), {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(`清理記憶失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== 控制面版 ====================

/** 取得控制面版聚合資料（統計/任務/存檔/審計/能力）。 */
export async function fetchDashboard(): Promise<DashboardData> {
  const resp = await fetch(apiUrl('/dashboard'));
  if (!resp.ok) throw new Error(`讀取控制面版失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 監控中心 OPC 快照（護欄 / 審計 / 即時標籤）。 */
export async function fetchOpcMonitor(): Promise<OpcMonitorData> {
  const resp = await fetch(apiUrl('/monitor/opc'));
  if (!resp.ok) throw new Error(`讀取 OPC 監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 監控中心 AI Hub 快照（探針 / 熔斷 / 呼叫日誌 / 預算）。 */
export async function fetchHubMonitor(): Promise<HubMonitorData> {
  const resp = await fetch(apiUrl('/monitor/hub'));
  if (!resp.ok) throw new Error(`讀取 Hub 監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 監控中心角色 Agent（每位公司角色獨立任務列表）。 */
export async function fetchAgentMonitor(): Promise<AgentMonitorData> {
  const resp = await fetch(apiUrl('/monitor/agents'));
  if (!resp.ok) throw new Error(`讀取角色 Agent 監控失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function updateAgentSettings(roleId: string, body: Record<string, unknown>): Promise<RoleAgent> {
  const resp = await fetch(apiUrl(`/monitor/agents/${encodeURIComponent(roleId)}/settings`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `更新角色設定失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function resetAgentSettings(roleId: string): Promise<RoleAgent> {
  const resp = await fetch(apiUrl(`/monitor/agents/${encodeURIComponent(roleId)}/reset`), { method: 'POST' });
  if (!resp.ok) throw new Error(`還原角色設定失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function createCustomAgent(body: Record<string, unknown>): Promise<RoleAgent> {
  const resp = await fetch(apiUrl('/monitor/agents'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `建立角色失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function deleteCustomAgent(roleId: string): Promise<void> {
  const resp = await fetch(apiUrl(`/monitor/agents/${encodeURIComponent(roleId)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(`刪除角色失敗（HTTP ${resp.status}）`);
}

export async function updateAgentMonitorPrefs(body: Partial<AgentMonitorPrefs>): Promise<AgentMonitorPrefs> {
  const resp = await fetch(apiUrl('/monitor/agents/prefs'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`更新監控偏好失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== Docker 容器管理 ====================

/** 獲取 Docker 狀態摘要（容器列表 + 健康檢查）。 */
export async function fetchDockerStatus(): Promise<DockerStatus> {
  const resp = await fetch(apiUrl('/docker/status'));
  if (!resp.ok) throw new Error(`讀取 Docker 狀態失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取 Docker 容器預算狀態（公司全權控制）。 */
export async function fetchDockerBudget(): Promise<DockerBudget> {
  const resp = await fetch(apiUrl('/docker/budget'));
  if (!resp.ok) throw new Error(`讀取 Docker 預算失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取容器資源使用統計。 */
export async function fetchDockerStats(): Promise<{ stats: Record<string, import('../types').DockerContainerStats> }> {
  const resp = await fetch(apiUrl('/docker/stats'));
  if (!resp.ok) throw new Error(`讀取 Docker 統計失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取指定服務日誌。 */
export async function fetchDockerLogs(service: string, tail: number = 100): Promise<{ service: string; tail: number; logs: string }> {
  const resp = await fetch(apiUrl(`/docker/logs/${encodeURIComponent(service)}?tail=${tail}`));
  if (!resp.ok) throw new Error(`讀取日誌失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 重啟指定服務。 */
export async function restartDockerService(service: string): Promise<DockerActionResult> {
  const resp = await fetch(apiUrl(`/docker/restart/${encodeURIComponent(service)}`), { method: 'POST' });
  if (!resp.ok) throw new Error(`重啟失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 停止指定服務。 */
export async function stopDockerService(service: string): Promise<DockerActionResult> {
  const resp = await fetch(apiUrl(`/docker/stop/${encodeURIComponent(service)}`), { method: 'POST' });
  if (!resp.ok) throw new Error(`停止失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 啟動指定服務。 */
export async function startDockerService(service: string): Promise<DockerActionResult> {
  const resp = await fetch(apiUrl(`/docker/start/${encodeURIComponent(service)}`), { method: 'POST' });
  if (!resp.ok) throw new Error(`啟動失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ═══════════════════════════════════════════════════════════
// 雲控制台 API
// ═══════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════
// 靈境積分帳務 API
// ═══════════════════════════════════════════════════════════

export async function fetchBilling(): Promise<BillingSnapshot> {
  const resp = await fetch(apiUrl('/billing'));
  if (!resp.ok) throw new Error(`讀取帳務失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchBillingLedger(limit = 50): Promise<{ user_id: string; entries: BillingLedgerEntry[] }> {
  const resp = await fetch(apiUrl(`/billing/ledger?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取分類帳失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function fetchBillingUsage(limit = 50): Promise<{ user_id: string; events: BillingUsageEvent[] }> {
  const resp = await fetch(apiUrl(`/billing/usage?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取用量失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function topupBillingCredits(credits: number, note = ''): Promise<unknown> {
  const resp = await fetch(apiUrl('/billing/topup'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credits, note }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `充值失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function assignBillingPlan(planId: string): Promise<unknown> {
  const resp = await fetch(apiUrl('/billing/assign-plan'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ plan_id: planId }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `方案切換失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function fetchBillingGrants(limit = 50) {
  const resp = await fetch(apiUrl(`/billing/grants?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取入帳來源失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ items: import('../types').BillingGrant[] }>;
}

export async function fetchBillingRollover(limit = 20) {
  const resp = await fetch(apiUrl(`/billing/rollover-records?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取滾存紀錄失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ items: Record<string, unknown>[] }>;
}

export async function fetchBillingAppeals(limit = 20) {
  const resp = await fetch(apiUrl(`/billing/appeals?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取申訴失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<{ appeals: import('../types').BillingAppeal[] }>;
}

export async function submitBillingAppeal(reason: string, detail: string, taskId = '') {
  const resp = await fetch(apiUrl('/billing/appeals'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason, detail, task_id: taskId }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `申訴失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function convertContribution(amount: number) {
  const resp = await fetch(apiUrl(`/billing/contribution/convert?amount=${amount}`), { method: 'POST' });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `轉換失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function lockContribution(amount: number, lockDays: number) {
  const resp = await fetch(apiUrl('/billing/contributor/contribution/lock'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount, lock_days: lockDays }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `鎖倉失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function fetchContributorStatus() {
  const resp = await fetch(apiUrl('/billing/contributor/contribution/status'));
  if (!resp.ok) throw new Error(`讀取貢獻狀態失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<import('../types').ContributionStatus>;
}

export async function fetchContributorEarnings() {
  const resp = await fetch(apiUrl('/billing/contributor/earnings'));
  if (!resp.ok) throw new Error(`讀取貢獻收益失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function bindContributorKey(encryptedKey: string, vendorId = 'self_host') {
  const resp = await fetch(apiUrl('/billing/contributor/bind-key'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ encrypted_key: encryptedKey, vendor_id: vendorId }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail || `綁定失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function triggerInstallments() {
  const resp = await fetch(apiUrl('/billing/contributor/contribution/unlock-installments'), { method: 'POST' });
  if (!resp.ok) throw new Error(`分期處理失敗（HTTP ${resp.status}）`);
  return resp.json();
}

type AdminHeaders = Record<string, string>;

function adminFetch(path: string, init: RequestInit = {}, headers: AdminHeaders = {}) {
  return fetch(apiUrl(path), {
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string>) },
  });
}

export async function adminListPricingConfigs(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/pricing-configs', {}, h);
  if (!resp.ok) throw new Error('讀取定價列表失敗');
  return resp.json();
}

export async function adminActivatePricing(version: number, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/pricing-configs/${version}/activate`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('啟用定價失敗');
  return resp.json();
}

export async function adminListCreditPolicies(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/credit-policies', {}, h);
  if (!resp.ok) throw new Error('讀取政策列表失敗');
  return resp.json();
}

export async function adminActivateCreditPolicy(version: number, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/credit-policies/${version}/activate`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('啟用政策失敗');
  return resp.json();
}

export async function adminListVendorConfigs(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/vendor-configs', {}, h);
  if (!resp.ok) throw new Error('讀取廠商配置失敗');
  return resp.json();
}

export async function adminActivateVendor(version: number, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/vendor-configs/${version}/activate`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('啟用廠商配置失敗');
  return resp.json();
}

export async function adminListAppeals(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/appeals', {}, h);
  if (!resp.ok) throw new Error('讀取申訴列表失敗');
  return resp.json();
}

export async function adminResolveAppeal(appealId: string, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/appeals/${appealId}/resolve`, { method: 'POST' }, h);
  if (!resp.ok) throw new Error('處理申訴失敗');
  return resp.json();
}

export async function adminRunRollover(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/rollover/run', { method: 'POST' }, h);
  if (!resp.ok) throw new Error('執行滾存失敗');
  return resp.json();
}

export async function adminListRollover(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/rollover-records', {}, h);
  if (!resp.ok) throw new Error('讀取滾存失敗');
  return resp.json();
}

export async function adminGetFaultPool(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/fault-pool', {}, h);
  if (!resp.ok) throw new Error('讀取 fault pool 失敗');
  return resp.json();
}

export async function adminGetCacheStats(h: AdminHeaders) {
  const resp = await adminFetch('/admin/billing/cache-stats', {}, h);
  if (!resp.ok) throw new Error('讀取快取統計失敗');
  return resp.json();
}

export async function adminGetTaskLedger(taskId: string, h: AdminHeaders) {
  const resp = await adminFetch(`/admin/billing/task-ledger/${taskId}`, {}, h);
  if (!resp.ok) throw new Error('讀取任務分類帳失敗');
  return resp.json();
}

/** @deprecated 使用 fetchBilling */
export const fetchWallet = fetchBilling;
export const fetchWalletLedger = fetchBillingLedger;
export const topupWallet = (amountUsd: number, note = '') => topupBillingCredits(amountUsd * 1000, note);

/** 獲取雲端費用摘要。 */
export async function fetchCloudBilling(): Promise<CloudBilling> {
  const resp = await fetch(apiUrl('/cloud/billing'));
  if (!resp.ok) throw new Error(`讀取費用失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取阿里雲 BSS 接入狀態與本月帳目。 */
export async function fetchCloudAliyun(): Promise<AliyunBilling> {
  const resp = await fetch(apiUrl('/cloud/aliyun'));
  if (!resp.ok) throw new Error(`讀取阿里雲帳目失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取資源監控歷史數據。 */
export async function fetchCloudMonitoring(range: string = '1h'): Promise<CloudMonitoring> {
  const resp = await fetch(apiUrl(`/cloud/monitoring?range=${range}`));
  if (!resp.ok) throw new Error(`讀取監控數據失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取最新資源快照。 */
export async function fetchCloudMonitoringLatest(): Promise<{ services: Record<string, { cpu: number; mem_mb: number }>; ts: string | null }> {
  const resp = await fetch(apiUrl('/cloud/monitoring/latest'));
  if (!resp.ok) throw new Error(`讀取最新快照失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取容器事件時間線。 */
export async function fetchCloudEvents(limit: number = 50): Promise<CloudEventsData> {
  const resp = await fetch(apiUrl(`/cloud/events?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取事件失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取告警規則與歷史。 */
export async function fetchCloudAlerts(): Promise<CloudAlertsData> {
  const resp = await fetch(apiUrl('/cloud/alerts'));
  if (!resp.ok) throw new Error(`讀取告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 創建告警規則。 */
export async function createAlertRule(rule: { name: string; metric: string; threshold: number; service: string }): Promise<Record<string, unknown>> {
  const resp = await fetch(apiUrl('/cloud/alerts'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(rule),
  });
  if (!resp.ok) throw new Error(`創建告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 切換告警規則啟用狀態。 */
export async function toggleAlertRule(ruleId: string): Promise<Record<string, unknown>> {
  const resp = await fetch(apiUrl(`/cloud/alerts/${encodeURIComponent(ruleId)}/toggle`), { method: 'POST' });
  if (!resp.ok) throw new Error(`切換告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 刪除告警規則。 */
export async function deleteAlertRule(ruleId: string): Promise<{ deleted: boolean }> {
  const resp = await fetch(apiUrl(`/cloud/alerts/${encodeURIComponent(ruleId)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(`刪除告警失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== AI Hub（/api/v1，不得剝除前綴） ====================

export const HUB_DEV_API_KEY = 'ak_live_hub_dev_key_for_local_only';

function hubUrl(path: string): string {
  const base: string = import.meta.env.VITE_API_URL ?? '/api';
  return `${base}/v1${path}`;
}

function hubHeaders(apiKey: string, extra?: Record<string, string>): HeadersInit {
  return {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json; charset=utf-8',
    ...extra,
  };
}

async function readHubError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: string; title?: string; code?: string };
    return body.detail || body.title || body.code || `HTTP ${resp.status}`;
  } catch {
    return `請求失敗（HTTP ${resp.status}）`;
  }
}

export interface HubModelInfo {
  id: string;
  provider: string;
  intelligence: number;
  price_in_per_1m: number;
  price_out_per_1m: number;
  price_cached_in_per_1m?: number | null;
  price_cache_write_per_1m?: number | null;
  price_reasoning_per_1m?: number | null;
  price_image_per_1m?: number | null;
  price_audio_per_1m?: number | null;
  cn_allowed: boolean;
  available_in_pool?: boolean;
}

export interface HubCatalog {
  models: HubModelInfo[];
  strategies: string[];
  default_chain: string[];
  cn_set: string[];
  race_pair: string[];
  quality_flagship: string;
  pool_lock?: {
    provider_kind: string;
    provider_label: string;
    lock_message: string;
    allowed_models: string[];
  };
}

export interface HubChatResult {
  id: string;
  model: string;
  chosen_provider: string;
  cost_usd: number;
  latency_ms: number;
  routing_strategy: string;
  failover_hops: number;
  cache: string;
  notice?: string;
  race?: boolean;
  choices: Array<{ message: { role: string; content: string }; finish_reason: string }>;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
}

export interface HubAgentCreateResult {
  task_id: string;
  status: string;
  poll_url: string;
  eta_ms: number;
}

export interface HubAgentTask {
  task_id: string;
  status: string;
  progress_pct: number;
  chosen_provider: string | null;
  cost_usd: number;
  latency_ms: number | null;
  trace_id?: string;
  result?: {
    content?: string;
    model?: string;
    failover_hops?: number;
    tool_traces?: Array<{
      tool: string;
      latency_ms: number;
      http_status: number;
      data?: Record<string, unknown>;
    }>;
  };
  error?: { code?: string; detail?: string };
}

export async function fetchHubCatalog(apiKey: string = HUB_DEV_API_KEY): Promise<HubCatalog> {
  const resp = await fetch(hubUrl('/catalog'), { headers: hubHeaders(apiKey) });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

export async function hubChatCompletion(opts: {
  apiKey?: string;
  prompt: string;
  strategy: string;
  region: string;
  model?: string;
  maxTokens?: number;
}): Promise<HubChatResult> {
  const extra: Record<string, string> = {
    'x-routing-strategy': opts.strategy,
    'X-Client-Region': opts.region,
  };
  const body: Record<string, unknown> = {
    messages: [{ role: 'user', content: opts.prompt }],
    temperature: 0.2,
    max_tokens: opts.maxTokens ?? 2048,
  };
  if (opts.model) body.model = opts.model;
  const resp = await fetch(hubUrl('/chat/completions'), {
    method: 'POST',
    headers: hubHeaders(opts.apiKey ?? HUB_DEV_API_KEY, extra),
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

export async function hubCreateAgentTask(opts: {
  apiKey?: string;
  input: string;
  tools?: string[];
  strategy?: string;
  region?: string;
}): Promise<HubAgentCreateResult> {
  const extra: Record<string, string> = {
    'x-routing-strategy': opts.strategy ?? 'quality_first',
    'X-Client-Region': opts.region ?? 'TW',
  };
  const resp = await fetch(hubUrl('/agent/tasks'), {
    method: 'POST',
    headers: hubHeaders(opts.apiKey ?? HUB_DEV_API_KEY, extra),
    body: JSON.stringify({
      input: opts.input,
      tools: opts.tools ?? ['StocksX_get_price'],
      timeout_seconds: 300,
    }),
  });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

export async function hubGetAgentTask(
  taskId: string,
  apiKey: string = HUB_DEV_API_KEY,
): Promise<HubAgentTask> {
  const resp = await fetch(hubUrl(`/agent/tasks/${encodeURIComponent(taskId)}`), {
    headers: hubHeaders(apiKey),
  });
  if (!resp.ok) throw new Error(await readHubError(resp));
  return resp.json();
}

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

// ==================== 數據庫連接池管理 ====================

export interface DbConnectionInfo {
  id: string;
  db_path: string;
  created_at: string;
  last_used_at: string;
  is_active: boolean;
  query_count: number;
  avg_latency_ms: number;
}

export interface DbPoolStats {
  pool_size: number;
  active_connections: number;
  idle_connections: number;
  total_queries: number;
  avg_query_latency_ms: number;
  connections: DbConnectionInfo[];
}

/** 獲取數據庫連接池統計信息 */
export async function fetchDbPoolStats(): Promise<DbPoolStats> {
  const resp = await fetch(apiUrl('/admin/db/pool/stats'));
  if (!resp.ok) throw new Error(`讀取連接池狀態失敗（HTTP ${resp.status}`);
  return resp.json();
}

/** 刷新連接池（關閉空閒連接） */
export async function refreshDbPool(min_idle: number = 2): Promise<DbPoolStats> {
  const resp = await fetch(apiUrl('/admin/db/pool/refresh'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ min_idle }),
  });
  if (!resp.ok) throw new Error(`刷新連接池失敗（HTTP ${resp.status}`);
  return resp.json();
}

/** 關閉指定連接 */
export async function closeDbConnection(connection_id: string): Promise<{ success: boolean }> {
  const resp = await fetch(apiUrl(`/admin/db/pool/connection/${encodeURIComponent(connection_id)}`), {
    method: 'DELETE',
  });
  if (!resp.ok) throw new Error(`關閉連接失敗（HTTP ${resp.status}`);
  return resp.json();
}

/** 執行健康檢查 */
export async function runDbHealthCheck(): Promise<{ healthy: boolean; details: string }> {
  const resp = await fetch(apiUrl('/admin/db/health'), {
    method: 'POST',
  });
  if (!resp.ok) throw new Error(`健康檢查失敗（HTTP ${resp.status}`);
  return resp.json();
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

async function readApiError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: string; error?: string };
    if (body.detail) return body.detail;
    if (body.error) return body.error;
  } catch {
    /* ignore */
  }
  return `請求失敗（HTTP ${resp.status}）`;
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


// ═══════════════════════════════════════════════════════════
// 技能庫 API（Skills）
// ═══════════════════════════════════════════════════════════

export interface SkillRecord {
  id: string;
  name: string;
  content: string;
  description: string;
  trigger: string;
  enabled: boolean;
  roles: string[];
  skill_budget: number;
  created_at: string;
  updated_at: string;
}

export interface SkillSaveBody {
  id?: string | null;
  name: string;
  content: string;
  description?: string;
  trigger?: string;
  enabled?: boolean;
  roles?: string[];
  skill_budget?: number;
}

export async function fetchSkills(): Promise<SkillRecord[]> {
  const resp = await fetch(apiUrl('/skills'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { skills: SkillRecord[] };
  return data.skills ?? [];
}

export async function saveSkill(body: SkillSaveBody): Promise<SkillRecord> {
  const resp = await fetch(apiUrl('/skills'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { skill: SkillRecord };
  return data.skill;
}

export async function toggleSkill(id: string): Promise<SkillRecord> {
  const resp = await fetch(apiUrl(`/skills/${encodeURIComponent(id)}/toggle`), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { skill: SkillRecord };
  return data.skill;
}

export async function deleteSkill(id: string): Promise<void> {
  const resp = await fetch(apiUrl(`/skills/${encodeURIComponent(id)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(await readApiError(resp));
}

export async function previewSkillPrompt(role?: string): Promise<{ role: string; prompt: string }> {
  const params = role ? `?role=${encodeURIComponent(role)}` : '';
  const resp = await fetch(apiUrl(`/skills/preview${params}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

// ═══════════════════════════════════════════════════════════
// MCP 連線管理 API
// ═══════════════════════════════════════════════════════════

export interface McpServerRecord {
  id: string;
  name: string;
  transport: 'stdio' | 'sse' | 'http';
  command: string;
  env: Record<string, string>;
  url: string;
  headers: Record<string, string>;
  enabled: boolean;
  allowed_tools: string[];
  readonly: boolean;
  timeout: number;
  created_at: string;
  updated_at: string;
  last_probe: McpProbeResult | Record<string, never>;
}

export interface McpProbeResult {
  ok: boolean;
  tool_count: number;
  tools: string[];
  latency_ms: number;
  probed_at: string;
  error: string;
}

export interface McpServerSaveBody {
  id?: string | null;
  name: string;
  transport: 'stdio' | 'sse' | 'http';
  command?: string;
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  enabled?: boolean;
  allowed_tools?: string[];
  readonly?: boolean;
  timeout?: number;
}

export async function fetchMcpServers(): Promise<McpServerRecord[]> {
  const resp = await fetch(apiUrl('/mcp/servers'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { servers: McpServerRecord[] };
  return data.servers ?? [];
}

export async function saveMcpServer(body: McpServerSaveBody): Promise<McpServerRecord> {
  const resp = await fetch(apiUrl('/mcp/servers'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { server: McpServerRecord };
  return data.server;
}

export async function toggleMcpServer(id: string): Promise<McpServerRecord> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}/toggle`), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { server: McpServerRecord };
  return data.server;
}

export async function deleteMcpServer(id: string): Promise<void> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(await readApiError(resp));
}

export async function probeMcpServer(id: string): Promise<McpProbeResult> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}/probe`), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function callMcpTool(id: string, tool: string, args: Record<string, unknown>): Promise<string> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}/call`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool, args }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { result: string };
  return data.result;
}

export async function mountMcpTools(): Promise<{ mounted: string[]; count: number }> {
  const resp = await fetch(apiUrl('/mcp/mount'), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}
