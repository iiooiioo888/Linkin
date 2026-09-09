/**
 * 任務詳情整頁的中文標籤表。
 * 與後端字面值對齊（backend/services/task_manager.py、company/state.py、
 * company/prompts.py 的需求審計輸出、company/raho/protocol.py）。
 */
import { COMPANY_TEMPLATES } from '../../types';

export const STATUS_META: Record<string, { label: string; tone: string }> = {
  pending: { label: '排隊中', tone: 'var(--apple-gray)' },
  running: { label: '執行中', tone: 'var(--apple-blue)' },
  completed: { label: '已完成', tone: 'var(--apple-green)' },
  failed: { label: '執行失敗', tone: 'var(--apple-red)' },
  cancelled: { label: '已取消', tone: 'var(--apple-gray)' },
  interrupted: { label: '中斷（服務重啟）', tone: 'var(--apple-orange)' },
};

/** 與 COMPANY_TEMPLATES（types.ts）同步的模板中文名。 */
export const COMPANY_TEMPLATE_LABEL: Record<string, string> = Object.fromEntries(
  (COMPANY_TEMPLATES as readonly { value: string; label: string }[]).map((t) => [t.value, t.label]),
);

export const STRATEGY_LABEL: Record<string, string> = {
  auto: 'auto（系統自動路由）',
  simple: 'simple（強制單次生成）',
  company: 'company（強制公司運行時）',
};

export const PATH_META: Record<string, { label: string; icon: string; tone: string }> = {
  simple: { label: '反思閉環', icon: '⚙', tone: 'var(--apple-blue-soft)' },
  company: { label: '公司運行時', icon: '🏢', tone: 'var(--apple-green)' },
  opc: { label: 'OPC 工業閉環', icon: '🏭', tone: 'var(--apple-orange)' },
  '': { label: '尚未路由', icon: '·', tone: 'var(--apple-tertiary)' },
};

/** 需求審計官門票狀態（backend/services/auditor.py）。 */
export const TICKET_STATUS_LABEL: Record<string, string> = {
  APPROVED_FOR_PLANNING: '已核准進入規劃',
  AUDITING: '審計中',
  FAILED: '審計失敗',
  REJECTED: '已退回',
  LOCKED: '已語義鎖定',
};

export function ticketStatusLabel(status?: string | null): string {
  if (!status) return '未紀錄';
  return TICKET_STATUS_LABEL[status] || status;
}

/** 門票欄位中文名（五維評分見 GrillUserCard 同一套措辭）。 */
export const DIMENSION_META: Array<{ key: 'specificity' | 'boundary' | 'constraints' | 'risk' | 'success'; label: string; note: string }> = [
  { key: 'specificity', label: '目標具體性', note: '主語＋謂語＋受詞＋量化結果' },
  { key: 'boundary', label: '邊界清晰度', note: '做什麼與絕對不做什麼' },
  { key: 'constraints', label: '約束量化度', note: '時間／預算／人力是否為數字' },
  { key: 'risk', label: '風險感知度', note: '是否預判主要失敗模式' },
  { key: 'success', label: '成功定義', note: '脫離主觀感受的客觀標準' },
];

/** 五維門檻：後端提示詞要求皆 > 90 才放行。 */
export const DIMENSION_GATE = 90;

export const BUDGET_LABELS: Array<{ key: string; label: string; group: 'task' | 'session' | 'month' | 'cost' | 'other' }> = [
  { key: 'task_spent', label: '本任務已花', group: 'task' },
  { key: 'task_limit', label: '本任務上限', group: 'task' },
  { key: 'task_api_spent', label: '本任務模型費', group: 'task' },
  { key: 'session_spent', label: '本會話已花', group: 'session' },
  { key: 'session_limit', label: '本會話上限', group: 'session' },
  { key: 'monthly_spent', label: '本月已花', group: 'month' },
  { key: 'monthly_limit', label: '本月上限', group: 'month' },
  { key: 'api_cost', label: '模型（API）費', group: 'cost' },
  { key: 'docker_cost', label: 'Docker 費', group: 'cost' },
  { key: 'aliyun_cost', label: '阿里雲費', group: 'cost' },
  { key: 'cloud_cost', label: '雲端合計', group: 'cost' },
  { key: 'total_spent', label: '總花費', group: 'cost' },
  { key: 'budget_pressure', label: '預算壓力', group: 'other' },
  { key: 'active_tier', label: '目前模型層', group: 'other' },
];

/** 與後端 BudgetConfig 對齊（company/state.py：warn 0.8 / degrade 0.9）。 */
export const BUDGET_WARN = 0.8;
export const BUDGET_DEGRADE = 0.9;

export const TIER_MODEL_LABEL: Record<string, string> = {
  critical: '關鍵層',
  reasoning: '推理層',
  routine: '日常層',
  summary: '摘要層',
};

/** 事件在時間軸上的語意著色。 */
export const EVENT_TONE: Record<string, string> = {
  work_item_error: 'var(--apple-red)',
  budget_warning: 'var(--apple-orange)',
  budget_degrade: 'var(--apple-orange)',
  review_rework: 'var(--apple-orange)',
  work_item_escalate: '#bf5af2',
};
