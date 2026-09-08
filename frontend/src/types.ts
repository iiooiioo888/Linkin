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
  updated_at?: string;
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
  auditor_ticket?: Record<string, unknown>;
}

/** 任務即時狀態（POST /tasks + GET /tasks/{id}） */
export interface TaskProgress {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
  /** 統一模式：執行策略（auto / simple / company） */
  strategy: 'auto' | 'simple' | 'company';
  /** 統一模式：實際解析的執行路徑（simple / company / opc） */
  resolved_path: 'simple' | 'company' | 'opc' | '';
  query: string;
  template: string;
  phase: string;
  events: TaskEvent[];
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

/** RAHO 用戶 Grill-Me 狀態 */
export interface GrillQuestion {
  question: string;
  why?: string;
  dimension?: string;
}

export interface AuditorScores {
  specificity?: number;
  boundary?: number;
  constraints?: number;
  risk?: number;
  success?: number;
}

export interface AuditorTicket {
  status?: string;
  confidence_score?: number;
  clarified_goal?: {
    target_audience?: string;
    core_action?: string;
    quantified_success?: string;
  };
  hard_constraints?: {
    deadline?: string;
    budget_range?: string;
    must_use_tech?: string[];
    absolute_exclusions?: string[];
  };
  risk_register?: {
    identified_risks?: string[];
    user_priority?: string;
  };
  audit_trail?: string[];
  dimension_scores?: AuditorScores;
}

export interface GrillUserState {
  session_id: string;
  locked: boolean;
  confidence: number;
  locked_brief?: string;
  should_grill?: boolean;
  question?: GrillQuestion | null;
  turns?: number;
  max_turns?: number;
  closed?: boolean;
  originalQuery?: string;
  history?: Array<{ role: 'assistant' | 'user'; content: string; why?: string }>;
  sendOptions?: {
    executionStrategy: 'auto' | 'simple' | 'company';
    companyTemplate: string;
    taskOptions?: TaskOptions;
  };
  phase?: number;
  phase_label?: string;
  phase_rounds?: number;
  scores?: AuditorScores;
  ticket?: AuditorTicket | null;
  terminated?: boolean;
  termination_reason?: string;
  termination_report?: string;
  status?: 'AUDITING' | 'APPROVED_FOR_PLANNING' | 'FAILED' | string;
  role?: string;
  role_label?: string;
}

export interface GrillTreeNode {
  node_id: string;
  from_layer: number;
  to_layer: number;
  kind: string;
  status: string;
  summary: string;
  created_at: number;
  resolved_at?: number | null;
  parent_id?: string | null;
  blocked?: boolean;
  payload?: Record<string, unknown>;
}

export interface GrillTree {
  tree_id: string;
  run_id: string;
  goal: string;
  created_at: number;
  nodes: GrillTreeNode[];
  open_count: number;
  blocked: GrillTreeNode[];
}

export interface RahoPendingDecision {
  decision_id: string;
  run_id: string;
  item_id: string;
  layer: number;
  question: string;
  choices: Array<{ key: string; label: string; rationale?: string }>;
  remaining_sec?: number;
  blocked?: boolean;
  resolved?: boolean;
}

export interface RahoSnapshot {
  trees?: GrillTree[];
  pending_decisions?: RahoPendingDecision[];
  blocked?: GrillTreeNode[];
  tree?: GrillTree | null;
  run_id?: string;
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

/** 聊天訊息模型 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  /** 模型思考／反思過程 */
  thinking?: string;
  /** 串流原始緩衝（含 think 標籤，僅生成中使用） */
  streamRaw?: string;
  /** 是否正在生成中 */
  streaming?: boolean;
  /** SSE 串流當前階段（標準模式打字機效果） */
  streamPhase?: string;
  /** 使用者回饋：1=👎 2=👍 */
  feedback?: 1 | 2;
  /** 統一模式執行策略 */
  executionStrategy?: 'auto' | 'simple' | 'company';
  /** 後台任務 ID */
  taskId?: string;
  /** 任務即時進度 */
  taskState?: TaskProgress;
  /** RAHO 用戶 Grill-Me 語意鎖定 */
  grill?: GrillUserState;
  /** 後端回傳的 metadata */
  meta?: {
    score?: number | null;
    iteration?: number;
    /** 多維度評估結果（優化 #1） */
    multiDim?: MultiDimEvaluation;
  };
}

/** 單一會話 */
export interface ChatSession {
  id: string;
  /** 會話標題（取第一則使用者訊息） */
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
}

/** 公司模式組織模板（對應後端 company_template） */
export const COMPANY_TEMPLATES = [
  { value: 'quick_task', label: '快速任務' },
  { value: 'page_dev', label: '頁面開發' },
  { value: 'fullstack_app', label: '全端開發' },
  { value: 'research_report', label: '研究報告' },
  { value: 'full_company', label: '完整公司' },
  { value: 'quant_desk', label: '量化研究桌' },
  { value: 'industrial_ops', label: '工業運維' },
  { value: 'story_studio', label: '故事工作室' },
] as const;

export type CompanyTemplate = (typeof COMPANY_TEMPLATES)[number]['value'];

// ==================== OPC 6 級閉環 ====================

/** OPC 6 級階段定義 */
export const OPC_PHASES: { key: string; label: string; icon: string }[] = [
  { key: 'sense_opc', label: '感知', icon: '📡' },
  { key: 'preprocess_opc', label: '預處理', icon: '🧹' },
  { key: 'analyze_opc', label: '分析', icon: '📊' },
  { key: 'diagnose_opc', label: '診斷', icon: '🔍' },
  { key: 'decide_opc', label: '決策', icon: '🧠' },
  { key: 'act_opc', label: '執行', icon: '⚡' },
];

/** OPC 6 級閉環完整狀態 */
export interface OPCState {
  sense?: {
    readings: Record<string, { value: unknown; data_type?: string; quality?: string }>;
    tag_count: number;
  };
  preprocess?: {
    quality_report: { total: number; good: number; bad: number; bad_tags?: string[] };
    clean_count: number;
  };
  analyze?: {
    stats: { min: number; max: number; avg: number; std: number; count: number };
    violations: Array<{ tag: string; value: number; threshold: number; direction: string; severity: string }>;
    trends: Record<string, string>;
    anomaly_tags: string[];
    summary: string;
  };
  diagnose?: {
    anomaly_detected: boolean;
    severity: string;
    analysis: string;
    root_cause: string;
    suggested_actions: Array<{ tag_name: string; value: number; reason: string }>;
  };
  decide?: {
    decisions: Array<{ tag_name: string; value: number; reason: string; priority: string; risk: string; risk_note?: string; order: number }>;
    summary: string;
  };
  act?: {
    actions: Array<{ tag_name: string; success: boolean; message?: string; written_value?: number }>;
    action_count: number;
    success_count: number;
  };
}

// ==================== 控制面版（GET /dashboard） ====================

/** 控制面版總覽統計 */
export interface DashboardStats {
  tasks_total: number;
  tasks_completed: number;
  tasks_failed: number;
  tasks_running: number;
  /** 成功率（0~100） */
  success_rate: number;
  avg_score: number | null;
  total_spent: number;
  total_iterations: number;
  archives_count: number;
  memories_count: number;
  opc_total: number;
  opc_blocked: number;
}

/** 任務摘要（控制面版任務歷史） */
export interface TaskSummary {
  task_id: string;
  query: string;
  /** 統一模式：執行策略 */
  strategy: string;
  /** 統一模式：實際執行路徑 */
  resolved_path: string;
  status: string;
  phase: string;
  score: number | null;
  iteration: number;
  spent: number;
  created_at: number;
  events_count: number;
  answer_preview: string;
  /** 最近任務附帶完整產出（控制台訊息串用） */
  answer?: string;
  /** 最近任務附帶事件流（最近 50 條） */
  events?: TaskEvent[];
  /** 任務耗時（秒） */
  duration_sec?: number;
}

/** 對話存檔記錄（AI 生成內容） */
export interface ArchiveRecord {
  timestamp: string;
  session_id: string;
  user_query: string;
  final_answer: string;
  evaluation_score: number | null;
  evaluation_feedback: string;
  reflection: unknown;
  memory_items: unknown[];
  metadata: Record<string, unknown>;
}

/** OPC 審計記錄 */
export interface AuditRecord {
  timestamp: string;
  operation: string;
  tag_name: string;
  value: unknown;
  reason: string;
  result: string;
  detail: string;
}

/** Agent 能力/工具註冊表項目（MCP/Skills 面版） */
export interface Capability {
  key: string;
  name: string;
  icon: string;
  description: string;
  status: string;
  stats: Record<string, unknown>;
}

/** GET /dashboard 回傳結構 */
export interface DashboardData {
  stats: DashboardStats;
  tasks: TaskSummary[];
  archives: ArchiveRecord[];
  opc_audit: { recent: AuditRecord[]; summary: Record<string, number> };
  capabilities: Capability[];
}

// ==================== Docker 容器管理 ====================

/** 单个容器信息 */
export interface DockerContainer {
  name: string;
  status: string;
  image: string;
  ports: string[];
  health: string;
  uptime: string;
  uptime_seconds: number;
  service: string;
}

/** 容器资源统计 */
export interface DockerContainerStats {
  cpu_percent: number;
  memory_usage: number;
  memory_limit: number;
  network_rx: number;
  network_tx: number;
  error?: string;
}

/** 单个服务健康信息 */
export interface DockerServiceHealth {
  healthy: boolean;
  status: string;
  health_detail: string;
}

/** 健康检查结果 */
export interface DockerHealth {
  all_healthy: boolean;
  services: Record<string, DockerServiceHealth>;
  _error?: string;
}

/** GET /docker/status 回傳 */
export interface DockerStatus {
  available: boolean;
  containers: DockerContainer[];
  health: DockerHealth;
  hourly_rates: Record<string, number>;
}

/** Docker 操作结果 */
export interface DockerActionResult {
  success: boolean;
  service: string;
  message: string;
}

/** Docker 预算状态（公司全权控制） */
export interface DockerBudgetService {
  service: string;
  rate_per_hour: number;
  uptime_hours: number;
  cost: number;
  status: 'running' | 'stopped';
}

export interface CompanyBudgetState {
  api_cost?: number;
  docker_cost: number;
  aliyun_cost?: number;
  cloud_cost?: number;
  total_spent: number;
  budget_pressure: number;
  optimization_suggestions: Array<{
    service: string;
    action: string;
    reason: string;
    estimated_saving_per_hour: number;
    priority: string;
  }>;
  auto_optimized: {
    stopped: string[];
    failed: string[];
    saved_per_hour: number;
  };
  last_updated: string;
}

/** GET /docker/budget 回传 */
export interface DockerBudget {
  available: boolean;
  services: DockerBudgetService[];
  total_docker_cost: number;
  total_hourly_rate: number;
  monthly_projection: number;
  company_budget: CompanyBudgetState;
}

// ==================== 雲控制台 ====================

/** 單服務費用明細 */
export interface CloudServiceCost {
  service: string;
  rate: number;
  uptime_hours: number;
  cost: number;
  source?: 'docker' | 'aliyun' | string;
  product_name?: string;
  pretax_amount_cny?: number;
}

/** 阿里雲 BSS 帳目摘要 */
export interface AliyunBilling {
  configured: boolean;
  ok: boolean;
  currency: string;
  cny_usd_rate: number;
  month_total_cny: number;
  month_total_usd: number;
  today_total_cny: number;
  today_total_usd: number;
  products: Array<{
    product_code: string;
    product_name: string;
    pretax_amount_cny: number;
    cost_usd: number;
    source?: string;
  }>;
  error: string | null;
  billing_cycle: string;
}

/** GET /cloud/billing 回傳 */
export interface CloudBilling {
  realtime: Record<string, number>;
  per_service: CloudServiceCost[];
  today_total: number;
  month_total: number;
  month_projected: number;
  total_now: number;
  docker?: {
    realtime: Record<string, number>;
    per_service: CloudServiceCost[];
    total_now: number;
    total_hourly_rate: number;
    month_projected: number;
  };
  aliyun?: AliyunBilling;
  breakdown?: {
    docker_usd: number;
    aliyun_usd: number;
    cloud_total_usd: number;
  };
}

/** 單服務資源數據點 */
export interface CloudServiceMetrics {
  cpu: number;
  mem_mb: number;
  mem_limit_mb: number;
  net_rx_mb: number;
  net_tx_mb: number;
}

/** 監控數據點 */
export interface CloudMonitorPoint {
  ts: string;
  services: Record<string, CloudServiceMetrics>;
}

/** GET /cloud/monitoring 回傳 */
export interface CloudMonitoring {
  points: CloudMonitorPoint[];
  range_hours: number;
  latest: CloudMonitorPoint | null;
}

/** 告警規則 */
export interface CloudAlertRule {
  id: string;
  name: string;
  metric: string;
  threshold: number;
  service: string;
  enabled: boolean;
  created_at: string;
}

/** 告警觸發記錄 */
export interface CloudAlertRecord {
  rule_id: string;
  rule_name: string;
  service: string;
  metric: string;
  value: number;
  threshold: number;
  ts: string;
}

/** GET /cloud/alerts 回傳 */
export interface CloudAlertsData {
  rules: CloudAlertRule[];
  history: CloudAlertRecord[];
}

/** 容器事件 */
export interface CloudEvent {
  ts: string;
  type: string;
  service: string;
  detail: string;
}

/** GET /cloud/events 回傳 */
export interface CloudEventsData {
  events: CloudEvent[];
}

// ==================== 監控中心（GET /monitor/opc · /monitor/hub · /monitor/agents） ====================

export interface OpcTagCatalog {
  name: string;
  unit: string;
  desc: string;
  range: number[];
  writable: boolean;
}

export interface OpcLiveReading {
  tag_name: string;
  value: unknown;
  data_type?: string;
  quality?: string;
  source_timestamp?: string | null;
}

export interface OpcMonitorData {
  guard: {
    write_whitelist: string[];
    write_bounds: Record<string, { min: number; max: number }>;
    require_approval: boolean;
    sim_enabled: boolean;
    opc_server: string;
  };
  catalog: OpcTagCatalog[];
  audit: { recent: AuditRecord[]; summary: Record<string, number> };
    live: {
    reachable: boolean;
    health: { status?: string; opc_connected?: boolean; opc_server?: string } | null;
    browse_tags: Array<Record<string, unknown>>;
    readings: OpcLiveReading[];
    simulated?: boolean;
    error: string | null;
  };
  recent_tasks: TaskProgress[];
  service_url: string;
}

export interface HubMonitorModel {
  id: string;
  provider: string;
  intelligence: number;
  latency_ewma_ms: number | null;
  ttfb_ms: number | null;
  price_in_per_1m: number | null;
  price_out_per_1m: number | null;
  consecutive_fail: number;
  ts?: number;
  available_in_pool?: boolean;
  mapped_model?: string;
  circuit: {
    state: string;
    fail_ratio?: number;
    window_calls?: number;
    open_cycles?: number;
    disabled?: boolean;
  };
}

export interface HubCallLog {
  id?: string;
  user_id?: string;
  session_id?: string;
  provider?: string;
  model_name?: string;
  prompt_tokens?: number;
  completion_tokens?: number;
  cost_usd?: number;
  status?: string;
  latency_ms?: number;
  error_code?: string;
  create_time?: string;
  trace_id?: string;
}

export interface HubMonitorData {
  cache: {
    hits: number;
    misses: number;
    hit_rate: number;
    target_hit_rate: number;
  };
  upstream_calls: number;
  call_log_count: number;
  call_logs: HubCallLog[];
  models: HubMonitorModel[];
  circuits: Record<string, HubMonitorModel['circuit']>;
  budgets: Array<{
    name: string;
    spent_today_usd: number;
    daily_limit_usd: number;
    monthly_limit_usd: number;
    remaining_today_usd: number;
  }>;
  agent_tasks: Array<{
    task_id: string;
    status: string;
    input: string;
    tools: string[];
    cost_usd: number;
    chosen_provider: string;
    latency_ms: number;
    progress_pct: number;
    error_code: string;
    trace_id: string;
    created_at: string | null;
  }>;
  routing: {
    default_chain: string[];
    cn_chain: string[];
    race_pair: string[];
    forbidden_vendor: string;
    pool_lock?: {
      provider_kind: string;
      provider_label: string;
      lock_message: string;
      allowed_models: string[];
    };
  };
}

export interface AgentWorkItem {
  id: string;
  title: string;
  description: string;
  status: string;
  kind: 'assigned' | 'review' | 'coordinate' | 'synthesize' | string;
  assignee: string | null;
  task_id: string;
  task_query: string;
  task_status: string;
  phase: string;
  cost_usd: number;
  estimated_cost?: number;
  output_preview: string;
  updated_at: string | null;
  source: 'live' | 'run_log' | string;
  depends_on?: string[];
  tier?: string;
  feedback?: unknown[];
}

export interface AgentEvent {
  ts: string | null;
  event: string;
  item_id?: string | null;
  title: string;
  assignee: string | null;
  task_id: string | null;
  cost_usd: number;
  score?: number | null;
  degraded?: boolean;
}

export interface AgentCompanyTask {
  task_id: string;
  query: string;
  status: string;
  phase: string;
}

export interface AgentMetrics {
  review_pass: number;
  review_rework: number;
  review_force: number;
  errors: number;
  tool_calls: number;
  budget_alerts: number;
  items_total?: number;
  success_rate?: number;
  avg_cost_usd?: number;
  capacity_pct?: number;
  daily_spent_usd?: number;
  /** API（LLM）用量花費 */
  api_spent_usd?: number;
  /** 雲資源（Docker + 阿里雲）分攤 */
  cloud_spent_usd?: number;
  avg_latency_ms?: number;
  tokens_in?: number;
  tokens_out?: number;
  last_model?: string;
  sla_breaches?: number;
  retries?: number;
  failovers?: number;
  cache_hits?: number;
  human_escalations?: number;
  p95_latency_ms?: number;
  weekly_spent_usd?: number;
  weekly_cloud_spent_usd?: number;
  grill_count?: number;
  grill_rate?: number;
  decision_clarity?: number;
}

export interface AgentAlert {
  level: 'info' | 'warning' | 'critical' | string;
  message: string;
}

export interface RolePreset {
  id: string;
  name: string;
  level: number;
  category: string;
  reporting_to?: string | null;
  system_prompt: string;
  responsibilities: string[];
  default_tier: string;
  hint?: string;
}

export interface LlmCatalogModel {
  id: string;
  name: string;
  owned_by: string;
  route_id?: string;
  route_name?: string;
}

export interface ApiRoutePublic {
  id: string;
  name: string;
  provider: string;
  provider_label: string;
  api_key: string;
  configured: boolean;
  api_base: string;
  model: string;
  allowed_models: string[];
  catalog: LlmCatalogModel[];
  catalog_source: string;
  catalog_error: string;
  catalog_fetched_at: string;
  catalog_url: string;
  weight: number;
  enabled: boolean;
  fallback: boolean;
  is_default: boolean;
  models_locked?: boolean;
  provider_routing?: Record<string, unknown> | null;
}

export interface ModelsByProvider {
  route_id: string;
  name: string;
  provider: string;
  provider_label: string;
  enabled: boolean;
  models: string[];
}

export interface OptimizationRoadmapItem {
  priority: string;
  id: string;
  label: string;
  benefit: string;
  enabled: boolean;
  status: string;
  metric?: string;
}

export interface OptimizationMonitorData {
  roadmap: OptimizationRoadmapItem[];
  stage_router: Record<string, { tier: string; model: string }>;
  reflection: {
    pass_threshold: number;
    max_iterations: number;
    min_score_improvement: number;
    dynamic_threshold?: Record<string, unknown>;
    sample_threshold_simple?: number;
    sample_threshold_complex?: number;
  };
  merge_review_synth: { enabled: boolean };
  llm_cache: {
    hits: number;
    misses: number;
    semantic_hits: number;
    evictions: number;
    hit_rate: number;
    semantic_enabled: boolean;
    max_size: number;
  };
  routing_feedback: {
    total: number;
    simple_count: number;
    company_count: number;
    simple_avg_score: number;
    company_avg_score: number;
    adaptive_length_threshold: number;
  };
  user_feedback?: {
    total: number;
    satisfaction_rate: number;
    stats?: Record<string, number>;
    thumbs_up?: number;
    thumbs_down?: number;
  };
  feedback_analysis?: {
    total: number;
    satisfaction_rate: number;
    signal_counts: Record<string, number>;
    score_buckets: { low: number; mid: number; high: number };
    avg_score: number | null;
    word_cloud: Array<{ word: string; count: number; weight: number }>;
    recent: Array<{
      session_id?: string;
      signal?: string;
      score?: number | null;
      comment?: string;
    }>;
  };
  model_calls?: {
    total_calls: number;
    total_cost: number;
    avg_duration_ms: number | null;
    files_scanned: number;
    by_model: Array<{
      model: string;
      count: number;
      share_pct: number;
      cost: number;
      avg_duration_ms: number | null;
    }>;
    by_phase: Array<{ phase: string; count: number; share_pct: number }>;
  };
  edge_cache?: {
    source?: string;
    tier: string;
    edge_ttl_sec: number;
    max_size?: number;
    hit_rate?: number;
    cache_age_sec: number | null;
    cache_fresh: boolean;
    entry_count: number;
    reading_count?: number;
  };
  /** @deprecated 請改用 edge_cache；保留向後相容 */
  opc_edge?: {
    tier: string;
    edge_ttl_sec: number;
    cache_age_sec: number | null;
    cache_fresh: boolean;
    reading_count: number;
    entry_count?: number;
    max_size?: number;
    hit_rate?: number;
  };
  system_stats?: {
    tasks_total: number;
    tasks_running: number;
    tasks_completed: number;
    tasks_failed: number;
    success_rate: number;
    avg_score: number | null;
    total_iterations: number;
  };
  trace: { trace_count: number; recent: Array<{ task_id?: string; event_count?: number }> };
  reflection_trace?: {
    tasks_analyzed: number;
    files_scanned: number;
    early_stop_count: number;
    avg_iterations: number | null;
    avg_score_delta: number | null;
    improvement_rate_pct: number;
    avg_evaluate_duration_ms: number | null;
    avg_reflection_duration_ms: number | null;
    avg_loop_duration_ms: number | null;
    recent_cycles: Array<{
      task_id: string;
      iterations: number;
      score_start: number | null;
      score_end: number | null;
      score_delta: number | null;
      evaluate_duration_ms: number;
      reflection_duration_ms: number;
      loop_duration_ms: number;
      early_stop: boolean;
      last_ts: string;
    }>;
  };
}

export interface LlmOpsData {
  provider_kind: string;
  provider_label: string;
  single_vendor: boolean;
  lock_message: string;
  model: string;
  api_base: string;
  configured: boolean;
  allowed_models: string[];
  catalog: LlmCatalogModel[];
  catalog_source: string;
  catalog_url: string;
  catalog_fetched_at: string;
  catalog_error: string;
  route_strategy?: string;
  default_route_id?: string;
  api_routes?: ApiRoutePublic[];
  models_by_provider?: ModelsByProvider[];
  route_strategies?: Array<{ id: string; label: string }>;
  provider_presets?: Array<{
    id: string;
    name: string;
    api_base: string;
    model: string;
    label: string;
  }>;
  ops: {
    refresh_interval_sec: number;
    last_ok_at: string;
    last_error: string;
    last_latency_ms: number;
    last_reason: string;
    consecutive_fail: number;
    stale: boolean;
    enabled: boolean;
    next_check_at?: string;
  };
}

export interface AgentCatalogMeta {
  categories: Array<{ id: string; label: string }>;
  tiers: Array<{ id: string; label: string }>;
  levels: Array<{ level: number; label: string }>;
  tool_names: string[];
  builtin_ids: string[];
  allowed_models?: string[];
  api_routes?: Array<{
    id: string;
    name: string;
    provider: string;
    provider_label: string;
    model: string;
    allowed_models: string[];
    enabled: boolean;
    configured?: boolean;
    is_default?: boolean;
  }>;
  models_by_provider?: ModelsByProvider[];
  model_token_hints?: Record<string, { max_context: number; max_output: number }>;
  routing_strategies?: Array<{ id: string; label: string }>;
  role_presets?: RolePreset[];
  org_templates?: Array<{ id: string; name: string; description: string; role_count: number }>;
}

export interface AgentMonitorPrefs {
  poll_interval_ms: number;
  show_disabled: boolean;
  show_idle: boolean;
  show_custom_only: boolean;
  group_by?: 'level' | 'category' | string;
  compact_cards?: boolean;
  default_desk_tab?: 'tasks' | 'monitor' | 'settings' | 'org' | string;
  sort_by?: 'level' | 'name' | 'status' | 'cost' | 'queue' | string;
  capacity_warn_pct?: number;
  show_prompt_preview?: boolean;
  highlight_alerts?: boolean;
  auto_open_busy?: boolean;
  default_layout?: 'catalog' | 'desk' | 'floor' | string;
  sound_on_alert?: boolean;
  show_cost_in_cards?: boolean;
  pin_role_ids?: string[];
  filter_min_level?: number;
  filter_max_level?: number;
  timezone?: string;
  show_on_call_only?: boolean;
}

export interface RoleAgent {
  id: string;
  name: string;
  level: number;
  level_label: string;
  category: string;
  reporting_to: string | null;
  can_delegate_to: string[];
  direct_reports: string[];
  responsibilities: string[];
  system_prompt?: string;
  max_parallel_work: number;
  default_tier: string;
  preferred_model?: string;
  preferred_provider?: string;
  daily_budget_usd?: number;
  weekly_budget_usd?: number;
  monthly_budget_usd?: number;
  cloud_daily_budget_usd?: number;
  cloud_weekly_budget_usd?: number;
  cloud_monthly_budget_usd?: number;
  tools_allowed?: string[];
  notes?: string;
  enabled?: boolean;
  is_custom?: boolean;
  is_builtin?: boolean;
  alert_on_error?: boolean;
  alert_on_budget?: boolean;
  alert_on_sla?: boolean;
  temperature?: number;
  max_output_tokens?: number;
  timeout_ms?: number;
  routing_strategy?: string;
  failover_models?: string[];
  sla_latency_ms?: number;
  max_retries?: number;
  language?: string;
  always_require_review?: boolean;
  priority?: number;
  description?: string;
  max_daily_items?: number;
  require_human_approval?: boolean;
  stream_enabled?: boolean;
  cache_enabled?: boolean;
  pii_redact?: boolean;
  mainland_only?: boolean;
  heartbeat_sec?: number;
  on_call?: boolean;
  tags?: string[];
  notify_channel?: string;
  quiet_hours?: string;
  context_window?: number;
  allow_tool_use?: boolean;
  auto_escalate?: boolean;
  templates: string[];
  alerts?: AgentAlert[];
  status: 'idle' | 'busy' | 'waiting' | 'error' | 'disabled' | string;
  inbox: Record<string, number>;
  queue: number;
  executing: number;
  done: number;
  blocked: number;
  cost_usd: number;
  /** API（LLM token）用量 */
  api_cost_usd?: number;
  /** 雲資源分攤合計（Docker + 阿里雲） */
  cloud_cost_usd?: number;
  docker_cost_usd?: number;
  aliyun_cost_usd?: number;
  last_activity_at: string | null;
  work_items: AgentWorkItem[];
  events: AgentEvent[];
  active_task_ids: string[];
  current_item: AgentWorkItem | null;
  company_tasks: AgentCompanyTask[];
  capacity_used: number;
  budget_remaining_usd?: number | null;
  budget_over?: boolean;
  ai_budget_remaining_usd?: number | null;
  ai_budget_over?: boolean;
  cloud_budget_remaining_usd?: number | null;
  cloud_budget_over?: boolean;
  metrics: AgentMetrics;
}

export interface AgentMonitorData {
  generated_at: string;
  summary: {
    roles_total: number;
    roles_busy: number;
    roles_waiting: number;
    roles_idle: number;
    roles_custom?: number;
    roles_disabled?: number;
    roles_enabled?: number;
    alerts_open?: number;
    work_items_open: number;
    work_items_done: number;
    company_tasks: number;
    running_company_tasks: number;
    total_cost_usd?: number;
    total_api_cost_usd?: number;
    total_cloud_cost_usd?: number;
    total_docker_cost_usd?: number;
    total_aliyun_cost_usd?: number;
    roles_on_call?: number;
    roles_need_approval?: number;
    roles_mainland_only?: number;
  };
  levels: Array<{ level: number; label: string }>;
  catalog_meta?: AgentCatalogMeta;
  monitor_prefs?: AgentMonitorPrefs;
  agents: RoleAgent[];
}
