/** 任務介面面板（參考 PysdnOPC 任務列表風格）。
 *
 * 公司模式：角色流水線芯片（Manager → 執行角色 → Reviewer →
 * Synthesizer）+ 子項三欄（隊列／執行中／已完成）+ 事件時間軸。
 * 標準模式：階段進度 + 評分軌跡。
 */
import { useMemo, useState } from 'react';
import type { TaskProgress, KanbanItem } from '../types';
import { OPC_PHASES } from '../types';
import { WORK_ITEM_COLUMNS, workItemColumnKey } from '../lib/agentUi';
import RahoDecisionBar from './RahoDecisionBar';
import { StatusColumnBoard } from './StatusColumnBoard';

interface TaskPanelProps {
  task: TaskProgress;
  /** 設定後顯示「開啟任務頁面」按鈕 */
  onOpenFull?: () => void;
  /** 取消任務回調 */
  onCancel?: (taskId: string) => void;
  /** 斷點續跑回調 */
  onResume?: (taskId: string) => void;
  /** 查看執行軌跡回調 */
  onOpenTrace?: (taskId: string) => void;
}

// ── 階段定義（匯出供整頁視圖复用） ──

export const STANDARD_PHASES: { key: string; label: string }[] = [
  { key: 'retrieve_memories', label: '記憶檢索' },
  { key: 'generate', label: '生成回答' },
  { key: 'evaluate', label: '自動評估' },
  { key: 'reflect', label: '反思' },
  { key: 'improve', label: '改進' },
  { key: 'done', label: '完成' },
];

export const COMPANY_PHASES: { key: string; label: string }[] = [
  { key: 'campaign_plan', label: '戰役規劃' },
  { key: 'decompose', label: '原子拆解' },
  { key: 'execute_review', label: '執行與審查' },
  { key: 'synthesize', label: '整合交付' },
  { key: 'final_review', label: '最終審查' },
  { key: 'evaluate', label: '品質評估' },
  { key: 'done', label: '完成' },
];

export { OPC_PHASES };

// ── 角色顯示名稱 ──

export const ROLE_LABELS: Record<string, string> = {
  manager: '專案經理',
  tech_lead: '技術主管',
  architect: '架構師',
  frontend_lead: '前端主管',
  backend_lead: '後端主管',
  test_lead: '測試主管',
  ui_designer: 'UI 設計師',
  css_dev: 'CSS 開發者',
  js_dev: 'JS 開發者',
  backend_dev: '後端開發者',
  tester: '測試工程師',
  devops: '維運工程師',
  reviewer: '審查者',
  synthesizer: '整合者',
  analyst: '分析師',
  coordinator: '協調者',
  developer: '通用開發者',
  security_lead: '資安主管',
  product_lead: '產品主管',
  data_lead: '資料主管',
  mobile_dev: '行動開發者',
  sre: '可靠性工程師',
  dba: '資料庫管理員',
  security_eng: '資安工程師',
  data_engineer: '資料工程師',
  tech_writer: '技術文件工程師',
  researcher: '研究員',
  prompt_engineer: 'Prompt 工程師',
  legal: '合規審查',
  content_writer: '內容撰寫',
  finance_lead: '金融主管',
  industrial_lead: '工業主管',
  creative_lead: '創意主管',
  quant_analyst: '量化分析師',
  crawler: '爬蟲工程師',
  opc_engineer: 'OPC 工業工程師',
  story_writer: '故事創作者',
  ux_researcher: 'UX 研究員',
  perf_eng: '效能工程師',
  translator: '在地化專員',
  support: '支援專員',
  platform_lead: '平台主管',
  github_ops: 'GitHub 工程師',
  release_eng: '發布工程師',
  hub_operator: 'Hub 值班',
  api_engineer: 'API 契約工程師',
  observability_eng: '可觀測性工程師',
  accessibility_eng: '無障礙工程師',
  product_designer: '產品設計師',
  risk_analyst: '風險分析師',
  market_data_eng: '行情工程師',
  narrative_editor: '敘事編輯',
  memory_curator: '記憶庫策展',
  knowledge_mgr: '知識庫管理員',
  ai_lead: 'AI 主管',
  growth_lead: '成長主管',
  ml_engineer: '機器學習工程師',
  data_scientist: '資料科學家',
  mlops: 'MLOps 工程師',
  rag_engineer: 'RAG 工程師',
  eval_engineer: '評測工程師',
  conversation_designer: '對話設計師',
  qa_automation: '自動化 QA',
  load_tester: '負載測試工程師',
  pen_tester: '滲透測試工程師',
  incident_cmd: '事故指揮官',
  chaos_eng: '混沌工程師',
  cloud_architect: '雲架構師',
  integration_eng: '整合工程師',
  feature_flag_eng: '功能開關工程師',
  cache_engineer: '快取工程師',
  plc_engineer: 'PLC 工程師',
  iot_engineer: 'IoT 工程師',
  portfolio_mgr: '投資組合經理',
  sentiment_analyst: '情緒分析師',
  billing_ops: '計費運維',
  router_eng: '路由工程師',
  copy_editor: '文案編輯',
  privacy_officer: '隱私長',
  customer_success: '客戶成功',
};

export function roleLabel(roleId: string): string {
  return ROLE_LABELS[roleId] ?? roleId.replace(/_/g, ' ');
}

// ── 角色狀態（對應 PysdnOPC 芯片圖標） ──

export type RoleStatus = 'pending' | 'active' | 'waiting' | 'done' | 'failed';

export function RoleIcon({ status }: { status: RoleStatus }) {
  if (status === 'done') return <span className="text-green-400">✓</span>;
  if (status === 'failed') return <span className="text-red-400">✗</span>;
  if (status === 'active') return <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-400 align-middle" />;
  if (status === 'waiting') return <span className="inline-block h-2 w-2 rounded-full bg-yellow-400/80 align-middle" />;
  return null;
}

export const ITEM_STATUS_META: Record<string, { label: string; cls: string; bar: string }> = {
  planning: { label: '規劃中', cls: 'bg-gray-700/60 text-gray-300', bar: 'bg-gray-500' },
  ready: { label: '就緒', cls: 'bg-blue-500/15 text-blue-300', bar: 'bg-blue-400' },
  executing: { label: '執行中', cls: 'bg-yellow-500/15 text-yellow-300', bar: 'bg-yellow-400' },
  in_review: { label: '審查中', cls: 'bg-purple-500/15 text-purple-300', bar: 'bg-purple-400' },
  rework: { label: '修改中', cls: 'bg-orange-500/15 text-orange-300', bar: 'bg-orange-400' },
  done: { label: '已完成', cls: 'bg-green-500/15 text-green-300', bar: 'bg-green-400' },
  blocked: { label: '阻塞', cls: 'bg-red-500/15 text-red-300', bar: 'bg-red-400' },
};

export const EVENT_LABELS: Record<string, string> = {
  company_start: '公司啟動',
  company_done: '公司流程完成',
  phase_change: '階段切換',
  decompose_done: '分解完成',
  work_item_start: '開始執行',
  work_item_done: '執行完成',
  work_item_error: '執行失敗',
  work_item_retry: '重試',
  work_item_escalate: '升級處理',
  execute_done: '執行完成',
  synthesize_done: '整合完成',
  final_review_done: '最終審查',
  review_approved: '審查通過',
  tool_call: '調用工具',
  tool_result: '工具結果',
  cancel_requested: '請求取消',
  review_pass: '審查通過',
  review_rework: '審查退回',
  review_force_done: '強制完成',
  budget_warning: '預算警告',
  budget_degrade: '預算降級',
  evaluation: '評估',
};

export function phaseIndex(phases: { key: string }[], phase: string): number {
  return phases.findIndex((p) => p.key === phase);
}

export function elapsed(ts: number): string {
  const sec = Math.floor((Date.now() - ts * 1000) / 1000);
  if (sec < 5) return '剛剛';
  if (sec < 60) return `${sec} 秒前`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分鐘前`;
  return `${Math.floor(min / 60)} 小時前`;
}

export default function TaskPanel({ task, onOpenFull, onCancel, onResume, onOpenTrace }: TaskPanelProps) {
  const [showTimeline, setShowTimeline] = useState(false);
  const [resuming, setResuming] = useState(false);
  const isCompany = task.resolved_path === 'company';
  const isOPC = task.resolved_path === 'opc';
  const isCancelled = task.status === 'cancelled';
  const phases = isOPC ? OPC_PHASES : isCompany ? COMPANY_PHASES : STANDARD_PHASES;
  const running = task.status === 'running' || task.status === 'pending';
  const failed = task.status === 'failed' || isCancelled;
  const currentIdx = phaseIndex(phases, task.phase);
  const phasePassed = (i: number) => (failed ? i < currentIdx : i < currentIdx || (!running && i <= currentIdx));

  // ── 公司模式：按角色分組工作項 ──
  const roleGroups = useMemo(() => {
    if (!isCompany) return [];
    const groups = new Map<string, { status: string; item: KanbanItem }[]>();
    for (const [status, items] of Object.entries(task.kanban)) {
      for (const item of items) {
        const role = item.assignee || 'developer';
        if (!groups.has(role)) groups.set(role, []);
        groups.get(role)!.push({ status, item });
      }
    }
    return [...groups.entries()].map(([role, entries]) => {
      const statusSet = new Set(entries.map((e) => e.status));
      let status: RoleStatus = 'pending';
      if (statusSet.has('executing')) status = 'active';
      else if (statusSet.has('blocked')) status = 'failed';
      else if (statusSet.has('in_review') || statusSet.has('rework') || statusSet.has('ready')) status = 'waiting';
      else if ([...statusSet].every((s) => s === 'done')) status = 'done';
      return { role, status, entries };
    });
  }, [isCompany, task.kanban]);

  // 流水線特殊角色狀態
  const managerStatus: RoleStatus =
    task.phase === 'decompose' || task.phase === 'final_review'
      ? 'active'
      : currentIdx > 0 || task.status === 'completed'
        ? 'done'
        : 'pending';
  const reviewerStatus: RoleStatus =
    (task.kanban.in_review?.length ?? 0) > 0
      ? 'active'
      : (task.kanban.done?.length ?? 0) > 0
        ? 'done'
        : 'pending';
  const synthesizerStatus: RoleStatus =
    task.phase === 'synthesize' ? 'active' : currentIdx > 2 || task.status === 'completed' ? 'done' : 'pending';

  // ── 流水線芯片（特殊角色只出現一次，工作項明細仍保留分組） ──
  const SPECIAL_ROLES = new Set(['manager', 'reviewer', 'synthesizer']);
  const pipeline: { key: string; label: string; status: RoleStatus }[] = isCompany
    ? [
        { key: 'manager', label: 'Manager', status: managerStatus },
        ...roleGroups
          .filter((g) => !SPECIAL_ROLES.has(g.role))
          .map((g) => ({ key: g.role, label: roleLabel(g.role), status: g.status })),
        { key: 'reviewer', label: 'Reviewer', status: reviewerStatus },
        { key: 'synthesizer', label: 'Synthesizer', status: synthesizerStatus },
      ]
    : [];

  const evaluations = task.events.filter((e) => e.event === 'evaluation');
  const doneCount = task.kanban.done?.length ?? 0;
  const totalCount = Object.values(task.kanban).reduce((s, items) => s + items.length, 0);

  // ── 工具調用狀態（Agent 工具閉環可視化）──
  const toolCalls = task.events.filter((e) => e.event === 'tool_call');
  const toolResults = task.events.filter((e) => e.event === 'tool_result');
  // 最近一次工具調用（用於執行中顯示）
  const lastToolCall = toolCalls[toolCalls.length - 1];
  const lastToolResult = toolResults[toolResults.length - 1];
  // 判斷最近調用是否仍在進行中（無對應結果）
  const toolPending = lastToolCall && (!lastToolResult || lastToolResult.ts < lastToolCall.ts);

  return (
    <div className="evo-task-card mb-2 w-full min-w-[240px] p-3 text-xs">
      {/* ── 標題列 ── */}
      <div className="flex items-center gap-2">
        {running && (
          <span className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
        )}
        {failed && <span>{isCancelled ? '🚫' : '❌'}</span>}
        {task.status === 'completed' && <span>✅</span>}
        <span className="font-medium text-gray-100">
          {isOPC ? '🏭 OPC 診斷' : isCompany ? '🏢 公司任務' : '⚙️ 反思任務'}
        </span>
        <span className="truncate text-gray-500">
          {running
            ? `${phases[currentIdx]?.label ?? task.phase}${totalCount > 0 ? ` · ${doneCount}/${totalCount} 工作項` : ''}`
            : isCancelled
              ? '已取消'
              : failed
                ? '執行失敗'
                : `評分 ${task.score ?? '-'} · 迭代 ${task.iteration}`}
        </span>
        {/* 取消按鈕：執行中且未請求取消時顯示 */}
        {running && !task.cancel_requested && onCancel && (
          <button
            onClick={() => onCancel(task.task_id)}
            className="ml-auto shrink-0 rounded border border-red-500/40 bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-300 transition-colors hover:bg-red-500/20"
          >
            ✕ 取消
          </button>
        )}
        {running && task.cancel_requested && (
          <span className="ml-auto shrink-0 text-[10px] text-yellow-400">取消中...</span>
        )}
        {/* 斷點續跑按鈕：任務失敗/取消且有檢查點時顯示 */}
        {!running && task.resumable && onResume && (
          <button
            onClick={() => {
              setResuming(true);
              onResume(task.task_id);
            }}
            disabled={resuming}
            className="ml-auto shrink-0 rounded border border-[#007AFF]/50 bg-[#007AFF]/10 px-1.5 py-0.5 text-[10px] text-[#64D2FF] transition-colors hover:bg-[#007AFF]/20 disabled:opacity-50"
          >
            {resuming ? '恢復中...' : '▶ 斷點續跑'}
          </button>
        )}
      </div>

      <RahoDecisionBar pending={task.raho?.pending_decisions ?? []} />

      {/* ── 階段進度條（執行中帶流光） ── */}
      <div className="mt-2.5 flex items-center gap-1">
        {phases.map((p, i) => {
          const active = running && i === currentIdx;
          return (
            <div key={p.key} className="flex flex-1 flex-col items-center gap-1">
              <div
                className={`h-1.5 w-full rounded-full transition-colors duration-300 ${
                  failed && i === currentIdx
                    ? 'bg-red-500'
                    : phasePassed(i)
                      ? 'bg-blue-500'
                      : active
                        ? 'progress-shimmer'
                        : 'bg-gray-700/70'
                }`}
              />
              <span
                className={`whitespace-nowrap text-[10px] ${
                  active ? 'text-blue-300' : phasePassed(i) ? 'text-gray-300' : 'text-gray-600'
                }`}
              >
                {p.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* ── 錯誤訊息 ── */}
      {failed && task.error && (
        <p className="mt-2 rounded-lg border border-red-500/25 bg-red-500/10 px-2.5 py-1.5 leading-relaxed text-red-300">⚠️ {task.error}</p>
      )}

      {/* ── Agent 工具調用狀態 ── */}
      {isCompany && toolCalls.length > 0 && (
        <div className="mt-2 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-2.5 py-1.5">
          <p className="flex items-center gap-1.5 text-[11px] text-cyan-300">
            {toolPending && (
              <span className="inline-block h-2.5 w-2.5 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
            )}
            🔧 {toolPending
              ? `正在調用工具 ${String(lastToolCall.data.tool ?? '')}...`
              : `已調用 ${toolCalls.length} 次工具`}
          </p>
          {!toolPending && lastToolResult && (
            <p className="mt-0.5 truncate text-[10px] text-gray-500">
              {lastToolResult.data.success ? '✓' : '✗'} {String(lastToolResult.data.tool ?? '')}
              {lastToolResult.data.observation ? `：${String(lastToolResult.data.observation).slice(0, 80)}` : ''}
            </p>
          )}
        </div>
      )}

      {/* ══ 公司模式：角色流水線（PysdnOPC 風格） ══ */}
      {isCompany && pipeline.length > 1 && (
        <div className="mt-3 flex flex-wrap items-center gap-1">
          {pipeline.map((role, i) => (
            <span key={role.key} className="flex items-center gap-1">
              <span
                className={`flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] transition-colors duration-200 ${
                  role.status === 'active'
                    ? 'border-blue-400/60 bg-blue-500/10 text-blue-200 shadow-[0_0_8px_rgba(59,130,246,0.25)]'
                    : role.status === 'done'
                      ? 'border-green-500/40 bg-green-500/10 text-green-200'
                      : role.status === 'failed'
                        ? 'border-red-500/40 bg-red-500/10 text-red-200'
                        : role.status === 'waiting'
                          ? 'border-yellow-500/40 bg-yellow-500/10 text-yellow-200'
                          : 'border-gray-700/70 bg-gray-800/40 text-gray-500'
                }`}
              >
                {role.label}
                <RoleIcon status={role.status} />
              </span>
              {i < pipeline.length - 1 && <span className="text-gray-600">→</span>}
            </span>
          ))}
        </div>
      )}

      {/* ══ 公司模式：子項三欄（隊列 / 執行中 / 已完成） ══ */}
      {isCompany && totalCount > 0 && (
        <div className="mt-2.5">
          <StatusColumnBoard
            compact
            columns={WORK_ITEM_COLUMNS.map((col) => {
              const entries = roleGroups
                .flatMap((g) => g.entries.map((e) => ({ ...e, role: g.role })))
                .filter((e) => workItemColumnKey(e.status) === col.key);
              return {
                key: col.key,
                label: col.label,
                count: entries.length,
                children: entries.map(({ status, item, role }) => {
                  const meta = ITEM_STATUS_META[status] ?? { label: status, cls: 'bg-gray-700/60 text-gray-300' };
                  const running = col.key === 'executing';
                  return (
                    <div key={item.id} className="rd-tc">
                      <div className="rd-tc-t">
                        <span className={`rd-od ${running ? 'run' : col.key === 'done' ? 'on' : 'off'}`} />
                        <span className="rd-tc-ttl">{item.title}</span>
                      </div>
                      <div className="rd-tc-m">
                        <span className={`rd-badge ${running ? 'run' : ''}`}>{meta.label}</span>
                        <span className="rd-tc-meta">{roleLabel(role)}</span>
                      </div>
                      {item.thinking?.trim() && (
                        <details className="mt-1.5">
                          <summary className="cursor-pointer text-[10px] text-[#636366]">思考過程</summary>
                          <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap font-sans text-[11px] leading-relaxed text-[#8E8E93]">
                            {item.thinking}
                          </pre>
                        </details>
                      )}
                      {item.output?.trim() && (
                        <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-[#8E8E93]">
                          {item.output}
                        </p>
                      )}
                    </div>
                  );
                }),
              };
            })}
          />
        </div>
      )}

      {/* ── 評分軌跡（多輪迭代時） ── */}
      {evaluations.length > 1 && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {evaluations.map((e, i) => (
            <span key={i} className="rounded-full bg-gray-800 px-2 py-0.5 text-[11px] text-gray-300">
              第 {Number(e.data.iteration ?? 0) + 1} 次：
              <span className="ml-1 font-medium text-blue-300">{String(e.data.score ?? '?')} 分</span>
            </span>
          ))}
        </div>
      )}

      {/* ══ 事件時間軸（可展開） ══ */}
      {isCompany && task.events.length > 0 && (
        <div className="mt-2.5">
          <button
            onClick={() => setShowTimeline((v) => !v)}
            className="text-[11px] text-gray-400 hover:text-gray-200"
          >
            {showTimeline ? '▲ 收合時間軸' : `▼ 事件時間軸（${task.events.length}）`}
          </button>
          {showTimeline && (
            <div className="task-expand-in relative mt-1.5 ml-1 border-l border-gray-700/70 pl-3.5">
              {task.events.slice(-10).map((e, i) => (
                <div key={i} className="relative mb-1 flex items-baseline gap-2 text-[11px] last:mb-0">
                  <span className={`absolute -left-[19px] top-1.5 h-1.5 w-1.5 rounded-full ${
                    e.event === 'work_item_error' ? 'bg-red-400'
                      : e.event === 'work_item_done' || e.event === 'review_pass' || e.event === 'company_done' ? 'bg-green-400'
                        : e.event === 'tool_call' || e.event === 'tool_result' ? 'bg-cyan-400'
                          : 'bg-blue-400/80'
                  }`} />
                  <span className="shrink-0 text-gray-300">{EVENT_LABELS[e.event] ?? e.event}</span>
                  <span className="min-w-0 flex-1 truncate text-gray-500">
                    {e.event === 'tool_call' || e.event === 'tool_result'
                      ? String(e.data.tool ?? '')
                      : String(e.data.title ?? e.data.phase ?? '')}
                  </span>
                  <span className="shrink-0 text-gray-600">{elapsed(e.ts)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── 預算 ── */}
      {isCompany && Object.keys(task.budget).length > 0 && (
        <p className="mt-2 text-[11px] text-gray-500">
          💰 花費 ${String(task.budget.task_spent ?? 0)} / 上限 ${String(task.budget.task_limit ?? '-')}
          <span className="ml-2">模型：{String(task.budget.active_tier ?? '-')}</span>
        </p>
      )}

      {/* ── 操作按鈕列 ── */}
      <div className="mt-2.5 flex gap-1.5">
        {onOpenFull && (
          <button
            onClick={onOpenFull}
            className="flex-1 rounded-lg border border-gray-700/70 bg-gray-800/40 py-1.5 text-[11px] font-medium text-gray-300 transition-all duration-200 hover:border-blue-500/70 hover:bg-blue-500/10 hover:text-blue-300 active:scale-[0.98]"
          >
            ⛶ 開啟任務頁面
          </button>
        )}
        {onOpenTrace && (
          <button
            onClick={() => onOpenTrace(task.task_id)}
            className="flex-1 rounded-lg border border-gray-700/70 bg-gray-800/40 py-1.5 text-[11px] font-medium text-gray-300 transition-all duration-200 hover:border-[#007AFF]/70 hover:bg-[#007AFF]/10 hover:text-[#64D2FF] active:scale-[0.98]"
          >
            📜 思考過程
          </button>
        )}
      </div>
    </div>
  );
}
