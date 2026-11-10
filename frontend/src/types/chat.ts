/** 聊天訊息、公司模板與 OPC 六級閉環階段型別。 */

import type { ChatBillingMeta } from '../lib/billingUi';
import type { BattlePlanState, GrillUserState } from './raho';
import type { MultiDimEvaluation, RoutingPreview, TaskProgress } from './task';

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
  /** L3 戰術指揮官作戰地圖 */
  battle?: BattlePlanState;
  /** 後端回傳的 metadata */
  meta?: {
    score?: number | null;
    iteration?: number;
    /** 多維度評估結果（優化 #1） */
    multiDim?: MultiDimEvaluation;
    /** 本輪調用資訊 footnote（Token 等，無金額） */
    billingFootnote?: string;
    /** 本輪 Token／模型收據 */
    billing?: ChatBillingMeta;
    /** 路由預覽／path_resolved 實際路徑（不含金額與 Token 數） */
    routingPreview?: RoutingPreview;
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

/** 舊任務曾把工業六級標成 opc 或 *_opc。新任務由任務經理分析，不再走這條階段。 */
export function usesIndustrialStages(task: {
  resolved_path?: string | null;
  template?: string | null;
  phase?: string | null;
} | null | undefined): boolean {
  if (!task) return false;
  if (task.resolved_path === 'opc') return true;
  return String(task.phase || '').endsWith('_opc');
}

/** 舊工業任務的階段（感知到執行）。新公司任務用任務分析與席位分工。 */
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
