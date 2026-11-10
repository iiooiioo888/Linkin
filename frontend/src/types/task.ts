/** 任務進度、多維度評估、思考軌跡與路由預覽型別。 */

import type { OPCState } from './chat';
import type { AuditorTicket, RahoSnapshot } from './raho';

/** 多維度評估（優化 #1） */
export interface DimensionScore {
  score: number;
  reason: string;
}

export interface MultiDimEvaluation {
  accuracy: DimensionScore;
  completeness: DimensionScore;
  clarity: DimensionScore;
  relevance: DimensionScore;
  overall: number;
  source: 'llm' | 'rule_fallback' | 'cross_model';
}

/** 任務進度事件 */
export interface TaskEvent {
  ts: number;
  event: string;
  data: Record<string, unknown>;
}

/** 看板上的工作項（含產出物與審查反饋） */
export interface KanbanItem {
  id: string;
  title: string;
  description?: string;
  assignee?: string | null;
  tier?: string;
  depends_on?: string[];
  actual_cost?: number;
  /** 最近審查反饋 */
  feedback?: Record<string, unknown>[];
  /** 產出物預覽 */
  output?: string;
  /** 角色思考過程 */
  thinking?: string;
  created_at?: string;
  updated_at?: string;
  completed_at?: string | null;
  tags?: string[];
  progress?: number;
  current_action?: string;
  files?: Array<{ name: string; path: string; status?: string; size?: string }>;
  tokens?: number;
}

/** 任務進階控制選項 */
export interface TaskOptions {
  /** 預算上限 */
  budget_limit?: number;
  /** 最大並行工作數 */
  max_parallel?: number;
  /** 最大迭代次數 */
  max_iterations?: number;
  /** 最大審查輪數 */
  max_review_rounds?: number;
  /** 通過門檻分數 */
  pass_threshold?: number;
  /** 模型層級偏好 */
  model_tier?: string;
  /** RAHO 語意鎖定簡報（取代原始 query 進入 Planner） */
  semantic_brief?: string;
  locked_brief?: string;
  /** 需求審計官核發的戰術指令 JSON */
  auditor_ticket?: AuditorTicket;
  /** 審計／L3 已產出的 L4+L3 規劃快照（避免任務內重算） */
  precomputed_planner?: Record<string, unknown>;
  /** 前端 i18n 語系（zh-TW / en） */
  ui_language?: string;
}

/** 任務即時狀態（POST /tasks + GET /tasks/{id}） */
export interface TaskProgress {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
  /** 統一模式：執行策略（auto / simple / company） */
  strategy: 'auto' | 'simple' | 'company';
  /** 統一模式：實際解析的執行路徑。工業執行的路徑標籤是 company */
  resolved_path: 'simple' | 'company' | 'opc' | 'minecraft_ops' | '';
  query: string;
  template: string;
  phase: string;
  events: TaskEvent[];
  /** 事件總數（後端可能因 events_limit 截斷） */
  events_total?: number;
  /** events 是否已被截斷 */
  events_truncated?: boolean;
  kanban: Record<string, KanbanItem[]>;
  budget: Record<string, unknown>;
  answer: string;
  score: number | null;
  iteration: number;
  error: string;
  /** 是否已請求取消 */
  cancel_requested?: boolean;
  /** 是否有可用的檢查點（可斷點續跑） */
  resumable?: boolean;
  /** TODO §9 單任務運行時狀態（C-UI-002） */
  runtime_state?: string;
  /** 進階控制選項 */
  options?: TaskOptions;
  /** 公司運行時：分解計劃 */
  plan?: {
    subtask_count?: number;
    strategy?: string;
    execution_plan?: unknown;
  } | null;
  /** 公司運行時：Manager 最終審查結果 */
  review?: Record<string, unknown> | null;
  /** 公司運行時：工作項統計 */
  stats?: Record<string, unknown> | null;
  /** OPC 6 級閉環狀態數據 */
  opc_state?: OPCState | null;
  /** 任務建立時間（Unix 秒） */
  created_at?: number;
  /** RAHO 質詢樹與待決決策 */
  raho?: RahoSnapshot;
}

// ==================== 思考過程軌跡 ====================

/** 思考過程軌跡事件 */
export interface TraceEntry {
  seq: number;
  ts: string;
  task_id: string;
  event: string;
  phase?: string;
  role?: string;
  item_id?: string;
  iteration?: number;
  model?: string | null;
  system?: string | null;
  prompt?: string;
  response?: string;
  prompt_length?: number;
  response_length?: number;
  cost?: number | null;
  duration_ms?: number | null;
  source?: string;
  query?: string;
  count?: number;
  items?: string[];
  score?: number | null;
  feedback?: string;
  strengths?: string;
  weaknesses?: string;
  raw_response?: string;
  reflection?: string;
  current_answer_preview?: string;
  improved_answer?: string;
  based_on_reflection?: string;
  tool?: string;
  args?: Record<string, unknown>;
  result?: string;
  success?: boolean;
  label?: string;
  state?: Record<string, unknown>;
  operation?: string;
  memory_id?: string;
  text?: string;
  metadata?: Record<string, unknown>;
  error?: string;
  recoverable?: boolean;
  context?: string;
  [key: string]: unknown;
}

/** 軌跡檔案摘要 */
export interface TraceSummary {
  task_id: string;
  event_count: number;
  first_ts: string;
  last_ts: string;
  file_size_kb: number;
}

/** 檢查點摘要 */
export interface CheckpointSummary {
  task_id: string;
  saved_at: string;
  goal: string;
  phase: string;
  config_name: string;
  work_item_count: number;
}

/** POST /routing/preview 與 SSE path_resolved 共用契約 */
export type RoutingPath = 'simple' | 'company' | 'opc' | 'minecraft_ops';
export type RoutingPreviewMode = 'auto' | 'simple' | 'company';
export type EstimatedCostLevel = 'low' | 'medium' | 'high';

export interface RoutingPreviewEstimatedCost {
  level: EstimatedCostLevel;
  est_tokens: number;
}

export interface RoutingPreview {
  path: RoutingPath;
  template: string | null;
  complexity: string;
  tier: string;
  model_hint: string;
  max_reflection_rounds: number;
  reason_codes: string[];
  estimated_cost: RoutingPreviewEstimatedCost;
}

export interface RoutingPreviewRequest {
  query: string;
  mode: RoutingPreviewMode;
  company_template?: string;
}
