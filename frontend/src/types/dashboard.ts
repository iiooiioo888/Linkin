// ==================== 控制面版（GET /dashboard） ====================

import type { TaskEvent } from './task';

/** 控制面版總覽統計 */
export interface DashboardStats {
  tasks_total: number;
  tasks_completed: number;
  tasks_failed: number;
  /** 僅 pending；tasks_running 仍含 pending+running 以相容舊欄位 */
  tasks_pending?: number;
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
