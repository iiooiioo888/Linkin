/** RAHO 質詢樹、L0 知識、作戰計畫與席位投遞型別。 */

import type { TaskOptions } from './task';

/** RAHO 用戶 Grill-Me 狀態 */
export interface GrillChoice {
  key: string;
  label: string;
}

export interface GrillQuestion {
  question: string;
  why?: string;
  dimension?: string;
  choices?: GrillChoice[];
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
  /** 後端門票為 JSON 字典，允許擴充欄位（前端 user_override 等）並與 Record<string, unknown> 互換 */
  [key: string]: unknown;
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
  planner?: Record<string, unknown> | null;
  terminated?: boolean;
  termination_reason?: string;
  termination_report?: string;
  status?: 'AUDITING' | 'APPROVED_FOR_PLANNING' | 'FAILED' | string;
  role?: string;
  role_label?: string;
  user_rounds?: number;
  l0?: L0Snapshot;
}

export interface GrillTreeNode {
  node_id: string;
  from_layer: number;
  to_layer: number;
  from_role?: string;
  to_role?: string;
  from_label?: string;
  to_label?: string;
  from_short?: string;
  to_short?: string;
  kind: string;
  kind_label?: string;
  status: string;
  summary: string;
  created_at: number;
  resolved_at?: number | null;
  parent_id?: string | null;
  blocked?: boolean;
  payload?: Record<string, unknown>;
}

export interface RahoDirectoryEntry {
  layer: number;
  id: string;
  role_id: string;
  title: string;
  short: string;
  full: string;
  lane?: 'command' | 'inspect' | 'kernel' | string;
  lane_label?: string;
  reports_to?: string | null;
  grill_targets?: string[];
  grill_target_labels?: string[];
  escalate_targets?: string[];
  escalate_target_labels?: string[];
  submit_targets?: string[];
  submit_target_labels?: string[];
  independent?: boolean;
}

export interface RahoGrillEdge {
  from_layer: number;
  to_layer: number;
  from_role: string;
  to_role: string;
  from_label?: string;
  to_label?: string;
  kind: string;
  label: string;
  direction: 'up' | 'down' | 'inspect' | 'inject' | string;
  lane?: string;
}

export interface L0KnowledgeEntity {
  id: string;
  content: string;
  metadata?: Record<string, unknown>;
  relations?: string[];
}

export interface L0MemoryTrace {
  task_id: string;
  layer: string;
  node_id: string;
  summary: string;
  decisions?: string[];
  failure_reason?: string;
  horizon?: 'stm' | 'mtm' | 'ltm' | string;
}

export interface L0Radar {
  timestamp?: number;
  metrics?: {
    token_usage_ratio?: number;
    avg_latency_ms?: number;
    grill_fail_rate?: number;
    pending_decisions?: number;
    external_market_sentiment?: string;
    user_urgency?: string;
  };
  bias_instructions?: string;
  energy_save?: boolean;
  pressure?: number;
}

export interface L0Snapshot {
  layer?: number;
  id?: string;
  role_id?: string;
  label?: string;
  short?: string;
  spine?: boolean;
  grill_targets?: string[];
  enabled?: boolean;
  query?: string;
  radar?: L0Radar;
  knowledge?: L0KnowledgeEntity[];
  traces?: L0MemoryTrace[];
  prefs?: Record<string, string>;
  directory?: RahoDirectoryEntry[];
  generated_at?: number;
}

export interface CampaignNode {
  node_id: string;
  title: string;
  outcome?: string;
  success_criteria?: string;
  depends_on?: string[];
  parallel_ok?: boolean;
}

export interface CampaignMap {
  goal?: string;
  nodes?: CampaignNode[];
  success_criteria?: string[];
  source?: string;
}

export interface BattleDagNode {
  node_id: string;
  description: string;
  depends_on?: string[];
  assigned_role_template?: string;
  parallel_ok?: boolean;
}

export interface AtomicRoleInstance {
  instance_id: string;
  node_id: string;
  template_id?: string;
  name?: string;
  trait?: string;
  system_prompt: string;
  allowed_tools?: string[];
  input_ref?: string | string[];
  output_schema?: string;
  success_criteria?: string;
  max_iterations?: number;
  token_budget?: number;
  failure_fallback?: string;
  l0_bias?: string;
}

export interface BattlePlan {
  plan_id?: string;
  based_on_l4_json?: string;
  rush_mode?: boolean;
  serial_depth?: number;
  parallel_roots?: string[];
  global_settings?: {
    default_model?: string;
    max_parallel_workers?: number;
    global_timeout_minutes?: number;
  };
  dag_nodes?: BattleDagNode[];
  atomic_role_instances?: AtomicRoleInstance[];
  reasoning?: BattleReasoning;
}

export interface BattleReasoning {
  parsing?: {
    core_action?: string;
    quantified_success?: string;
    deadline?: string;
    absolute_exclusions?: string[];
    identified_risks?: string[];
  };
  topology?: {
    parallel?: string[];
    sequential?: string[];
    serial_depth?: number;
    rush_mode?: boolean;
  };
  templating?: Array<{
    node_id?: string;
    template?: string;
    name?: string;
    trait?: string;
    fallback?: string;
  }>;
  budgeting?: Array<{
    instance_id?: string;
    max_iterations?: number;
    token_budget?: number;
  }>;
}

export interface BattleChecklistItem {
  id: string;
  label: string;
  pass: boolean;
  rush_mode?: boolean;
  hours_until_deadline?: number | null;
}

export interface BattlePlanState {
  status: 'PLAN_READY' | 'REJECT_TO_L4' | 'ESCALATE_TO_USER' | string;
  role_label?: string;
  rush_mode?: boolean;
  reason?: string;
  defects?: string[];
  details?: string;
  suggested_alternatives?: string[];
  waiting_for_user_decision?: boolean;
  l0?: L0Snapshot;
  waiting_for_l4?: boolean;
  battle_plan?: BattlePlan | null;
  battle_plan_yaml?: string;
  reasoning?: BattleReasoning;
  node_count?: number;
  serial_depth?: number;
  checklist?: {
    ok?: boolean;
    defects?: string[];
    items?: BattleChecklistItem[];
    rush_mode?: boolean;
  };
}

export interface GrillTree {
  tree_id: string;
  run_id: string;
  goal: string;
  created_at: number;
  nodes: GrillTreeNode[];
  open_count: number;
  blocked: GrillTreeNode[];
  campaign?: CampaignMap;
}

export interface RahoPendingDecision {
  decision_id: string;
  run_id: string;
  item_id: string;
  layer: number;
  layer_label?: string;
  role_id?: string;
  role_label?: string;
  question: string;
  choices: Array<{ key: string; label: string; rationale?: string }>;
  created_at?: number;
  ttl?: number;
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
  campaign?: CampaignMap;
  directory?: RahoDirectoryEntry[];
  grill_chain?: RahoGrillEdge[];
  kind_labels?: Record<string, string>;
  direction_labels?: Record<string, string>;
  lane_labels?: Record<string, string>;
  raho_graph?: {
    chain?: number[];
    command_chain?: number[];
    inspect_chain?: number[];
    kernel_chain?: number[];
    lanes?: Record<string, { id: string; label: string; layers: number[] }>;
    layers?: RahoDirectoryEntry[];
    edges?: RahoGrillEdge[];
    kind_labels?: Record<string, string>;
    direction_labels?: Record<string, string>;
    lane_labels?: Record<string, string>;
  };
  l0?: L0Snapshot;
}

// ═══════════════════════════════════════════════════════════════
// 席位投遞 I/O（公司運行時監察頁）
// ═══════════════════════════════════════════════════════════════

/** 席位投遞種類：decompose／execute／rework／review／synthesize／final_review／inspect */
export type SeatIOKind =
  | 'decompose'
  | 'execute'
  | 'rework'
  | 'review'
  | 'synthesize'
  | 'final_review'
  | 'inspect'
  | string;

/** 一次投遞的輸入來源分解（回答「這段 prompt 是哪些部分拼起來的」） */
export interface SeatIOContextSource {
  kind: string;
  label: string;
  chars: number;
  preview: string;
}

/** 單次席位投遞全文（GET /monitor/raho/seat/{io_id}、feed?full=true） */
export interface SeatIORecord {
  io_id: string;
  ts: string;
  epoch: number;
  run_id: string;
  task_id: string;
  item_id: string;
  title: string;
  role: string;
  role_label: string;
  layer: number | null;
  layer_label: string;
  lane: string;
  kind: SeatIOKind;
  attempt: number;
  step: number;
  tool_steps: number;
  final: boolean;
  model: string;
  tier: string;
  temperature?: number | null;
  system: string;
  prompt: string;
  response: string;
  system_length: number;
  prompt_length: number;
  response_length: number;
  truncated: boolean;
  cost_usd: number | null;
  duration_ms: number | null;
  error: string;
  degraded: boolean;
  allowed_tools: string[];
  input_ref?: string | string[] | null;
  output_schema: string;
  success_criteria: string;
  context_sources: SeatIOContextSource[];
}

/** 列表用輕量投影：正文換成預覽＋長度 */
export type SeatIOFeedRow = Omit<SeatIORecord, 'system' | 'prompt' | 'response'> & {
  system_preview?: string;
  prompt_preview?: string;
  response_preview?: string;
};

/** GET /monitor/raho/feed 回應 */
export interface SeatIOFeed {
  items: SeatIOFeedRow[];
  /** memory＝環形緩衝；disk＝持久 seat_*.jsonl（進程重啟後） */
  source: 'memory' | 'disk' | string;
  runs: Array<{
    run_id: string;
    task_id: string;
    invocations: number;
    roles: string[];
    items: string[];
    first_ts: string;
    last_ts: string;
    total_cost_usd: number;
    role_count: number;
    item_count: number;
  }>;
  total_roles: number;
}

export interface SeatFeedQuery {
  task_id?: string;
  run_id?: string;
  role?: string;
  layer?: number;
  item_id?: string;
  kind?: SeatIOKind;
  limit?: number;
  full?: boolean;
}
