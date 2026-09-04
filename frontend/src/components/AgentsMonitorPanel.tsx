/**
 * AgentsMonitorPanel — 每位公司角色一張獨立 Agent 工作台。
 *
 * 預設進入選中角色的完整介面：任務列表 + 看板 + 事件 + 組織監控。
 * 樓層總覽改為次要視圖。
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  createCustomAgent,
  deleteCustomAgent,
  fetchAgentMonitor,
  resetAgentSettings,
  updateAgentMonitorPrefs,
  updateAgentSettings,
} from '../api/client';
import {
  AGENT_STATUS_META,
  CATEGORY_LABEL,
  ROUTING_LABEL,
  TIER_LABEL,
  agentOpenCount,
  blankMetrics,
  fmtUsd,
  fmtWhen,
  JUMP_AGENT_EVENT,
  isAlertAgent,
  isLiveAgent,
  pickDefaultAgentId,
  type JumpAgentDetail,
} from '../lib/agentUi';
import { AGENT_FALLBACK_ROSTER } from '../lib/monitorFallbacks';
import type { AgentEvent, AgentMonitorData, AgentWorkItem, RoleAgent } from '../types';
import RoleSettingsPanel, { CreateRoleModal, draftToPayload, type RoleSettingsDraft } from './RoleSettingsPanel';
import { EVENT_LABELS, ITEM_STATUS_META, roleLabel } from './TaskPanel';

const KIND_META: Record<string, { label: string; cls: string }> = {
  assigned: { label: '指派', cls: 'bg-[#007AFF]/15 text-[#64D2FF]' },
  review: { label: '審查', cls: 'bg-purple-500/15 text-purple-300' },
  coordinate: { label: '協調', cls: 'bg-amber-500/15 text-amber-300' },
  synthesize: { label: '整合', cls: 'bg-cyan-500/15 text-cyan-300' },
};

const KANBAN: Array<{ key: string; label: string; statuses: string[] }> = [
  { key: 'queue', label: '佇列', statuses: ['planning', 'ready'] },
  { key: 'executing', label: '執行中', statuses: ['executing'] },
  { key: 'review', label: '審查 / 返工', statuses: ['in_review', 'rework'] },
  { key: 'closed', label: '完成 / 阻塞', statuses: ['done', 'blocked'] },
];

const LIST_FILTERS: Array<{ key: string; label: string; statuses?: string[] }> = [
  { key: 'open', label: '進行中', statuses: ['planning', 'ready', 'executing', 'in_review', 'rework', 'blocked'] },
  { key: 'all', label: '全部' },
  { key: 'assigned', label: '指派' },
  { key: 'review', label: '審查' },
  { key: 'done', label: '完成', statuses: ['done'] },
];

function eventLabel(event: string): string {
  return EVENT_LABELS[event] ?? event.replace(/_/g, ' ');
}

function itemStatus(status: string): { label: string; cls: string } {
  return ITEM_STATUS_META[status] ?? { label: status, cls: 'bg-gray-700/60 text-gray-300' };
}

function currentItem(agent: RoleAgent): AgentWorkItem | null {
  const executing = agent.work_items.find((i) => i.status === 'executing');
  if (executing) return executing;
  if (
    agent.current_item &&
    ['executing', 'planning', 'ready', 'in_review', 'rework'].includes(agent.current_item.status)
  ) {
    return agent.current_item;
  }
  return null;
}

function Kpi({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: 'green' | 'blue' | 'orange' | 'amber' | 'violet' | 'red';
}) {
  const valueCls =
    accent === 'green'
      ? 'text-[#34C759]'
      : accent === 'blue'
        ? 'text-[#007AFF]'
        : accent === 'orange'
          ? 'text-[#FF9500]'
          : accent === 'amber'
            ? 'text-[#FF9500]'
            : accent === 'violet'
              ? 'text-[#64D2FF]'
              : accent === 'red'
                ? 'text-[#FF3B30]'
                : 'text-[#F5F5F7]';
  return (
    <div className="min-w-0 apple-card apple-card--tight apple-card--pad">
      <p className="apple-title truncate">{label}</p>
      <p className={`apple-data mt-2 truncate text-[18px] ${valueCls}`}>{value}</p>
      {hint && <p className="mt-1.5 truncate text-[11px] font-normal text-[#8E8E93]">{hint}</p>}
    </div>
  );
}

/** 分組卡片容器：標題固定 + 內容可捲 */
function CardSection({
  title,
  hint,
  children,
  className = '',
  scroll = false,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  className?: string;
  scroll?: boolean;
}) {
  return (
    <section className={`apple-card ${className}`}>
      <div className="apple-card__head">
        <h4 className="apple-title">{title}</h4>
        {hint && <span className="text-[10px] font-normal text-[#636366]">{hint}</span>}
      </div>
      <div className={`apple-card__body ${scroll ? '' : 'apple-card__body--static'}`}>
        {children}
      </div>
    </section>
  );
}

/** Agent 預算組成：合計 = API + Docker + 阿里雲 */
function BudgetCostCards({
  agent,
  cols = 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5',
}: {
  agent: RoleAgent;
  cols?: string;
}) {
  const m = agent.metrics ?? blankMetrics();
  const api = m.api_spent_usd ?? agent.api_cost_usd ?? 0;
  const docker = agent.docker_cost_usd ?? 0;
  const aliyun = agent.aliyun_cost_usd ?? 0;
  const cloud = m.cloud_spent_usd ?? agent.cloud_cost_usd ?? docker + aliyun;
  const total = m.daily_spent_usd ?? agent.cost_usd ?? api + cloud;
  const budget = agent.daily_budget_usd ?? 0;
  return (
    <div className={`grid gap-2 ${cols}`}>
      <Kpi label="合計花費" value={fmtUsd(total)} hint="API＋雲資源" accent="amber" />
      <Kpi label="API 用量" value={fmtUsd(api)} hint="LLM token" accent="violet" />
      <Kpi label="Docker" value={fmtUsd(docker)} hint="本地容器分攤" accent="blue" />
      <Kpi label="阿里雲" value={fmtUsd(aliyun)} hint="BSS 帳目分攤" accent="orange" />
      <Kpi
        label="日預算"
        value={budget > 0 ? fmtUsd(budget) : '不限'}
        hint={
          agent.budget_over
            ? '已超支'
            : agent.budget_remaining_usd != null
              ? `剩餘 ${fmtUsd(agent.budget_remaining_usd)}`
              : '含 API＋雲'
        }
        accent={agent.budget_over ? 'red' : 'green'}
      />
    </div>
  );
}

function WorkItemCard({
  item,
  expanded,
  onToggle,
  compact,
}: {
  item: AgentWorkItem;
  expanded?: boolean;
  onToggle?: () => void;
  compact?: boolean;
}) {
  const st = itemStatus(item.status);
  const kind = KIND_META[item.kind] ?? KIND_META.assigned;
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`w-full apple-card apple-card--tight !p-0 px-3 py-2 text-left ${
        onToggle ? 'hover:border-[#34343a]' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className={`min-w-0 font-medium text-[#f7f8f8] ${compact ? 'truncate text-[12px]' : 'text-[13px]'}`}>
          {item.title}
        </p>
        <div className="flex shrink-0 items-center gap-1">
          {!compact && <span className={`rounded px-1.5 py-0.5 text-[10px] ${kind.cls}`}>{kind.label}</span>}
          <span className={`rounded px-1.5 py-0.5 text-[10px] ${st.cls}`}>{st.label}</span>
        </div>
      </div>
      {!compact && (
        <p className="mt-0.5 truncate text-[11px] text-[#8a8f98]">
          {item.task_query || item.task_id}
          {item.assignee && item.kind !== 'assigned' ? ` · 原指派 ${roleLabel(item.assignee)}` : ''}
        </p>
      )}
      {expanded && (
        <div className="mt-2 space-y-1.5 border-t border-white/[0.08] pt-2">
          {item.description && <p className="text-[11px] leading-relaxed text-[#d0d6e0]">{item.description}</p>}
          {item.output_preview && (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-[#141516] px-2 py-1 font-mono text-[10px] text-[#d0d6e0]">
              {item.output_preview}
            </pre>
          )}
          {(item.depends_on?.length ?? 0) > 0 && (
            <p className="text-[10px] text-[#8a8f98]">依賴 {item.depends_on!.join(', ')}</p>
          )}
          <div className="flex justify-between text-[10px] text-[#62666d]">
            <span>
              {fmtUsd(item.cost_usd)} · {item.source === 'live' ? '即時' : '歷史'}
              {item.tier ? ` · ${TIER_LABEL[item.tier] ?? item.tier}` : ''}
            </span>
            <span>{fmtWhen(item.updated_at)}</span>
          </div>
        </div>
      )}
      {!expanded && compact && (
        <p className="mt-1 text-[10px] text-[#62666d]">{fmtWhen(item.updated_at)}</p>
      )}
    </button>
  );
}

function EventRow({ event }: { event: AgentEvent }) {
  return (
    <div className="flex gap-2 border-b border-white/[0.08] py-1.5 last:border-0">
      <span className="w-24 shrink-0 font-mono text-[10px] text-[#62666d]">{fmtWhen(event.ts)}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] text-[#d0d6e0]">{eventLabel(event.event)}</p>
        {event.title && <p className="truncate text-[10px] text-[#8a8f98]">{event.title}</p>}
      </div>
      {event.cost_usd > 0 && (
        <span className="shrink-0 font-mono text-[10px] text-[#8a8f98]">{fmtUsd(event.cost_usd)}</span>
      )}
    </div>
  );
}

function RoleChips({
  ids,
  onOpen,
}: {
  ids: string[];
  onOpen: (id: string) => void;
}) {
  if (ids.length === 0) return <span className="text-[11px] text-[#62666d]">無</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          onClick={() => onOpen(id)}
          className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98] hover:border-[#007AFF]/40 hover:text-[#64D2FF]"
        >
          {roleLabel(id)}
        </button>
      ))}
    </div>
  );
}

function RoleMonitorExtras({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  if (agent.id === 'reviewer') {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="通過" value={String(m.review_pass)} />
        <Kpi label="退回" value={String(m.review_rework)} />
        <Kpi label="強制完成" value={String(m.review_force)} />
      </div>
    );
  }
  if (agent.id === 'manager') {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="協調任務" value={String(agent.company_tasks.length)} hint="本角色經手" />
        <Kpi label="預算告警" value={String(m.budget_alerts)} />
        <Kpi label="錯誤" value={String(m.errors)} />
      </div>
    );
  }
  if (agent.id === 'synthesizer') {
    const outputs = agent.work_items.filter((i) => i.kind === 'synthesize' && i.output_preview);
    return (
      <div className="apple-card apple-card--tight !p-0 px-3 py-2">
        <p className="text-[10px] uppercase tracking-wider text-[#62666d]">最近整合產出</p>
        {outputs.length === 0 ? (
          <p className="mt-1 text-[11px] text-[#62666d]">尚無整合結果</p>
        ) : (
          outputs.slice(0, 2).map((item) => (
            <p key={`${item.task_id}-${item.id}`} className="mt-1 line-clamp-3 text-[11px] text-[#d0d6e0]">
              {item.output_preview}
            </p>
          ))
        )}
      </div>
    );
  }
  if (agent.id === 'coordinator') {
    return (
      <div className="grid grid-cols-2 gap-2">
        <Kpi label="阻塞項" value={String(agent.blocked)} hint="待解除" />
        <Kpi label="工具呼叫" value={String(m.tool_calls)} />
      </div>
    );
  }
  if (agent.category === 'finance' || agent.id.includes('quant')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="研究項" value={String(agent.work_items.length)} />
        <Kpi label="花費" value={fmtUsd(agent.cost_usd)} />
        <Kpi label="模型" value={m.last_model || agent.preferred_model || '預設'} />
      </div>
    );
  }
  if (agent.category === 'industrial' || agent.id.includes('opc')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="診斷項" value={String(agent.work_items.length)} />
        <Kpi label="錯誤" value={String(m.errors)} />
        <Kpi label="SLA 逾時" value={String(m.sla_breaches ?? 0)} />
      </div>
    );
  }
  if (agent.category === 'creative' || agent.id.includes('story')) {
    return (
      <div className="grid grid-cols-2 gap-2">
        <Kpi label="章節／文案" value={String(agent.work_items.length)} />
        <Kpi label="完成" value={String(agent.done)} />
      </div>
    );
  }
  if (agent.category === 'crawler') {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="採集任務" value={String(agent.work_items.length)} />
        <Kpi label="重試" value={String(m.retries ?? 0)} />
        <Kpi label="錯誤" value={String(m.errors)} />
      </div>
    );
  }
  if (agent.category === 'platform' || agent.id.includes('github') || agent.id.includes('release')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="倉庫工作" value={String(agent.work_items.length)} />
        <Kpi label="工具呼叫" value={String(m.tool_calls)} />
        <Kpi label="錯誤" value={String(m.errors)} />
      </div>
    );
  }
  if (agent.category === 'hub' || agent.id.includes('hub')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="預算告警" value={String(m.budget_alerts)} />
        <Kpi label="今日花費" value={fmtUsd(m.daily_spent_usd ?? agent.cost_usd)} />
        <Kpi label="熔斷／錯誤" value={String(m.errors)} />
      </div>
    );
  }
  if (agent.category === 'memory' || agent.id.includes('memory') || agent.id.includes('knowledge')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="策展項" value={String(agent.work_items.length)} />
        <Kpi label="完成" value={String(agent.done)} />
        <Kpi label="重試" value={String(m.retries ?? 0)} />
      </div>
    );
  }
  if (agent.category === 'ai' || agent.id.includes('rag') || agent.id.includes('eval') || agent.id.includes('ml')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="評測／實驗" value={String(agent.work_items.length)} />
        <Kpi label="快取命中" value={String(m.cache_hits ?? 0)} />
        <Kpi label="故障轉移" value={String(m.failovers ?? 0)} />
      </div>
    );
  }
  if (agent.category === 'growth' || agent.id.includes('customer')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="漏斗項" value={String(agent.work_items.length)} />
        <Kpi label="完成" value={String(agent.done)} />
        <Kpi label="升級" value={String(m.human_escalations ?? 0)} />
      </div>
    );
  }
  if (agent.category === 'security' || agent.id.includes('pen') || agent.id.includes('privacy')) {
    return (
      <div className="grid grid-cols-3 gap-2">
        <Kpi label="審查項" value={String(agent.work_items.length)} />
        <Kpi label="錯誤" value={String(m.errors)} />
        <Kpi label="PII" value={agent.pii_redact === false ? '關' : '開'} />
      </div>
    );
  }
  return (
    <div className="grid grid-cols-3 gap-2">
      <Kpi label="工具呼叫" value={String(m.tool_calls)} />
      <Kpi label="錯誤" value={String(m.errors)} />
      <Kpi
        label="容量"
        value={`${agent.capacity_used ?? agent.executing}/${agent.max_parallel_work}`}
        hint="執行中 / 並行上限"
      />
    </div>
  );
}

function RoleDeepMonitor({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  return (
    <div className="space-y-3">
      <CardSection title="預算組成" hint="合計 = API＋Docker＋阿里雲">
        <BudgetCostCards agent={agent} />
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Kpi
            label="週／月預算"
            value={`${fmtUsd(agent.weekly_budget_usd ?? 0)} / ${fmtUsd(agent.monthly_budget_usd ?? 0)}`}
            hint="0 = 不限"
          />
          <Kpi label="平均成本" value={fmtUsd(m.avg_cost_usd ?? 0)} hint="每工作項" />
          <Kpi
            label="預算告警"
            value={agent.alert_on_budget === false ? '關' : '開'}
            hint={agent.budget_over ? '目前超支' : '監控中'}
            accent={agent.budget_over ? 'red' : undefined}
          />
        </div>
      </CardSection>

      <CardSection title="模型與路由">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Kpi label="指定模型" value={agent.preferred_model || (TIER_LABEL[agent.default_tier] ?? agent.default_tier)} />
          <Kpi label="路由" value={ROUTING_LABEL[agent.routing_strategy || ''] ?? (agent.routing_strategy || '品質')} />
          <Kpi label="故障轉移" value={String(agent.failover_models?.length ?? 0)} hint={(agent.failover_models ?? []).slice(0, 2).join(' → ') || '未設'} />
          <Kpi label="Token" value={`${m.tokens_in ?? 0} / ${m.tokens_out ?? 0}`} hint="in / out" />
          <Kpi label="快取命中" value={String(m.cache_hits ?? 0)} hint={agent.cache_enabled === false ? '快取關' : '快取開'} />
          <Kpi label="允許工具" value={String(agent.tools_allowed?.length ?? 0)} hint={(agent.tools_allowed ?? []).slice(0, 2).join(' · ') || '未限'} />
        </div>
      </CardSection>

      <CardSection title="效能與 SLA">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Kpi label="平均延遲" value={`${Math.round(m.avg_latency_ms ?? 0)} ms`} hint={`重試 ${m.retries ?? 0}`} />
          <Kpi label="P95 延遲" value={`${Math.round(m.p95_latency_ms ?? 0)} ms`} hint={`failover ${m.failovers ?? 0}`} />
          <Kpi label="SLA 逾時" value={String(m.sla_breaches ?? 0)} hint={agent.sla_latency_ms ? `${agent.sla_latency_ms}ms` : '未設'} />
          <Kpi label="成功率" value={`${m.success_rate ?? 0}%`} hint={`${m.items_total ?? 0} 項`} accent="green" />
          <Kpi label="容量使用" value={`${m.capacity_pct ?? 0}%`} hint={`${agent.capacity_used ?? agent.executing}/${agent.max_parallel_work}`} />
          <Kpi label="人工升級" value={String(m.human_escalations ?? 0)} hint={agent.require_human_approval ? '需核准' : '自動'} />
        </div>
      </CardSection>

      <CardSection title="角色與合規">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Kpi label="狀態" value={agent.enabled === false ? '停用' : '啟用'} hint={agent.is_custom ? '自定義' : '內建'} />
          <Kpi label="分類" value={CATEGORY_LABEL[agent.category] ?? agent.category} hint={`L${agent.level} · P${agent.priority ?? 3}`} />
          <Kpi label="語言" value={agent.language || 'zh-TW'} hint={agent.always_require_review ? '一律審查' : '審查可選'} />
          <Kpi label="值班" value={agent.on_call ? 'On-call' : '否'} hint={agent.quiet_hours || '無安靜時段'} />
          <Kpi label="合規" value={agent.mainland_only ? '僅國內' : '全球'} hint={agent.pii_redact === false ? 'PII 關' : 'PII 開'} />
          <Kpi label="日工作上限" value={agent.max_daily_items ? String(agent.max_daily_items) : '不限'} hint={`心跳 ${agent.heartbeat_sec ?? 0}s`} />
          <Kpi label="告警開關" value={agent.alert_on_error === false ? '錯誤關' : '錯誤開'} hint={agent.alert_on_budget === false ? '預算關' : '預算開'} />
          <Kpi label="標籤" value={String(agent.tags?.length ?? 0)} hint={(agent.tags ?? []).slice(0, 3).join(' · ') || '無'} />
        </div>
      </CardSection>

      {(agent.alerts?.length ?? 0) > 0 && (
        <CardSection title="角色告警" className="border-amber-500/20 bg-amber-500/5">
          <div className="space-y-1">
            {agent.alerts!.map((al, i) => (
              <p key={`${al.message}-${i}`} className="text-[11px] text-amber-100">
                {al.level} · {al.message}
              </p>
            ))}
          </div>
        </CardSection>
      )}
      {agent.system_prompt && (
        <CardSection title="角色設定摘要">
          <p className="line-clamp-6 whitespace-pre-wrap text-[11px] leading-relaxed text-[#d0d6e0]">{agent.system_prompt}</p>
        </CardSection>
      )}
    </div>
  );
}

function AgentDeskCard({
  agent,
  onOpen,
  showPrompt,
  showCost,
  compact,
  highlighted,
}: {
  agent: RoleAgent;
  onOpen: () => void;
  showPrompt?: boolean;
  showCost?: boolean;
  compact?: boolean;
  highlighted?: boolean;
}) {
  const meta = AGENT_STATUS_META[agent.status] ?? AGENT_STATUS_META.idle;
  const open = agentOpenCount(agent);
  const now = currentItem(agent);
  const previewLimit = compact ? 2 : 3;
  const preview = agent.work_items.slice(0, previewLimit);

  return (
    <button
      type="button"
      id={`role-card-${agent.id}`}
      onClick={onOpen}
      className={`flex h-full w-full min-h-0 min-w-0 flex-col apple-card px-3 py-3 text-left transition-colors hover:border-white/15 ${
        compact ? 'gap-2' : 'gap-2.5'
      } ${
        highlighted
          ? 'border-[#007AFF]/60 ring-1 ring-[#007AFF]/40'
          : agent.status === 'busy'
            ? 'border-[#4cc38a]/30'
            : agent.status === 'error'
              ? 'border-red-500/30'
              : 'border-white/[0.08]'
      }`}
    >
      <div className="flex min-w-0 items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#141516] text-[11px] font-medium text-[#d0d6e0]">
            {agent.name.slice(0, 1)}
            <span className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ${meta.dot}`} />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[13px] text-[#f7f8f8]">{agent.name}</span>
            <span className={`block truncate text-[10px] ${meta.text}`}>
              {meta.label}
              {open > 0 ? ` · ${open} 開放` : ' · 待命'}
              {agent.on_call ? ' · 值班' : ''}
            </span>
          </span>
        </div>
        {(agent.cost_usd ?? 0) > 0 && showCost !== false && (
          <p
            className="shrink-0 whitespace-nowrap font-mono text-[10px] text-amber-300/90"
            title="此角色合計花費（API＋Docker＋阿里雲）"
          >
            {fmtUsd(agent.cost_usd)}
          </p>
        )}
      </div>

      {showPrompt && (agent.description || agent.system_prompt) && !compact && (
        <p className="line-clamp-2 min-h-[2.5em] text-[10px] leading-relaxed text-[#8a8f98]">
          {agent.description || agent.system_prompt}
        </p>
      )}

      {now && (
        <p className="truncate rounded bg-[#141516] px-2 py-1 text-[11px] text-[#d0d6e0]">
          進行中 · {now.title}
        </p>
      )}

      <div className="grid grid-cols-4 gap-1 text-center">
        {[
          ['佇列', agent.queue],
          ['執行', agent.executing],
          ['審查', agent.inbox.in_review ?? 0],
          ['完成', agent.done],
        ].map(([label, value]) => (
          <div key={String(label)} className="min-w-0 rounded bg-[#141516] px-1 py-1">
            <p className="font-mono text-[12px] text-[#f7f8f8]">{value}</p>
            <p className="truncate text-[9px] text-[#62666d]">{label}</p>
          </div>
        ))}
      </div>

      {showCost !== false &&
        !compact &&
        ((agent.api_cost_usd ?? 0) > 0 || (agent.docker_cost_usd ?? 0) > 0 || (agent.aliyun_cost_usd ?? 0) > 0) && (
        <div className="grid grid-cols-3 gap-1">
          <div className="min-w-0 rounded bg-[#141516] px-1.5 py-1 text-center">
            <p className="truncate font-mono text-[10px] text-[#64D2FF]">{fmtUsd(agent.api_cost_usd ?? 0)}</p>
            <p className="text-[8px] text-[#62666d]">API</p>
          </div>
          <div className="min-w-0 rounded bg-[#141516] px-1.5 py-1 text-center">
            <p className="truncate font-mono text-[10px] text-sky-300">{fmtUsd(agent.docker_cost_usd ?? 0)}</p>
            <p className="text-[8px] text-[#62666d]">Docker</p>
          </div>
          <div className="min-w-0 rounded bg-[#141516] px-1.5 py-1 text-center">
            <p className="truncate font-mono text-[10px] text-orange-300">{fmtUsd(agent.aliyun_cost_usd ?? 0)}</p>
            <p className="text-[8px] text-[#62666d]">阿里雲</p>
          </div>
        </div>
      )}

      <div className="mt-auto flex flex-col justify-start gap-1">
        {preview.length === 0 ? (
          <p className="rounded border border-dashed border-white/[0.08] px-2 py-2 text-center text-[11px] text-[#62666d]">
            尚無工作項
          </p>
        ) : (
          preview.map((item) => {
            const st = itemStatus(item.status);
            return (
              <div
                key={`${item.task_id}-${item.id}-${item.kind}`}
                className="flex min-w-0 items-center justify-between gap-2 rounded bg-[#141516] px-2 py-1"
              >
                <span className="min-w-0 truncate text-[11px] text-[#d0d6e0]">{item.title}</span>
                <span className={`shrink-0 rounded px-1 py-0.5 text-[9px] ${st.cls}`}>{st.label}</span>
              </div>
            );
          })
        )}
        {agent.work_items.length > previewLimit && (
          <p className="text-[10px] text-[#62666d]">還有 {agent.work_items.length - previewLimit} 項…</p>
        )}
      </div>
    </button>
  );
}

interface AgentsMonitorPanelProps {
  focusAgentId?: string | null;
  onFocusAgent?: (id: string | null) => void;
}

export default function AgentsMonitorPanel({ focusAgentId, onFocusAgent }: AgentsMonitorPanelProps) {
  const [data, setData] = useState<AgentMonitorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>(focusAgentId || 'manager');
  /** 預設工作台：85 位名冊統一在左側外圍 SidePanel，主區不重複當目錄 */
  const [layout, setLayout] = useState<'desk' | 'floor' | 'catalog'>('desk');
  const [overviewMode, setOverviewMode] = useState<'list' | 'cards'>('list');
  const [filter, setFilter] = useState<'all' | 'live' | 'alert'>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [itemFilter, setItemFilter] = useState<string>('open');
  const [boardMode, setBoardMode] = useState<'list' | 'kanban'>('list');
  const [deskTab, setDeskTab] = useState<'tasks' | 'monitor' | 'settings' | 'org'>('tasks');
  const [query, setQuery] = useState('');
  const [rosterFilter, setRosterFilter] = useState<'all' | 'custom' | 'disabled' | 'oncall'>('all');
  const [creating, setCreating] = useState(false);
  const [cloneFrom, setCloneFrom] = useState<RoleAgent | null>(null);
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [didAutoOpen, setDidAutoOpen] = useState(false);
  const [appliedDefaultTab, setAppliedDefaultTab] = useState(false);
  const [appliedDefaultLayout, setAppliedDefaultLayout] = useState(false);
  const overviewScrollRef = useRef<HTMLDivElement | null>(null);

  const scrollToRoleTarget = useCallback((id?: string, level?: number) => {
    const run = () => {
      const el =
        (id ? document.getElementById(`role-card-${id}`) : null) ??
        (typeof level === 'number' ? document.getElementById(`role-level-${level}`) : null);
      el?.scrollIntoView({ behavior: 'smooth', block: id ? 'center' : 'start' });
    };
    requestAnimationFrame(run);
    window.setTimeout(run, 160);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchAgentMonitor();
      setData(next);
      setError(null);
      setSelectedId((current) => pickDefaultAgentId(next.agents, focusAgentId || current));
    } catch (err) {
      setError((err as Error).message);
    }
  }, [focusAgentId]);

  const pollMs = data?.monitor_prefs?.poll_interval_ms ?? 5000;

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), Math.max(2000, pollMs));
    return () => clearInterval(timer);
  }, [refresh, pollMs]);

  useEffect(() => {
    if (focusAgentId) setSelectedId(focusAgentId);
  }, [focusAgentId]);

  useEffect(() => {
    const onJump = (event: Event) => {
      const { id, level } = (event as CustomEvent<JumpAgentDetail>).detail ?? {};
      if (id) setSelectedId(id);
      const jumpingLevel = typeof level === 'number' && !id;
      if (jumpingLevel) {
        setLayout((cur) => (cur === 'desk' ? (overviewMode === 'cards' ? 'floor' : 'catalog') : cur));
      }
      if (layout === 'desk' && !jumpingLevel) return;
      scrollToRoleTarget(id, level);
    };
    window.addEventListener(JUMP_AGENT_EVENT, onJump);
    return () => window.removeEventListener(JUMP_AGENT_EVENT, onJump);
  }, [layout, overviewMode, scrollToRoleTarget]);

  useEffect(() => {
    if (didAutoOpen || !data?.monitor_prefs?.auto_open_busy || focusAgentId) return;
    const busy = data.agents.find((a) => a.status === 'busy');
    if (busy) {
      setSelectedId(busy.id);
      setLayout('desk');
      setDidAutoOpen(true);
    }
  }, [data?.monitor_prefs?.auto_open_busy, data?.agents, focusAgentId, didAutoOpen]);

  useEffect(() => {
    if (appliedDefaultTab) return;
    const tab = data?.monitor_prefs?.default_desk_tab;
    if (tab === 'tasks' || tab === 'monitor' || tab === 'settings' || tab === 'org') {
      setDeskTab(tab);
      setAppliedDefaultTab(true);
    }
  }, [appliedDefaultTab, data?.monitor_prefs?.default_desk_tab]);

  useEffect(() => {
    if (appliedDefaultLayout || focusAgentId) return;
    const next = data?.monitor_prefs?.default_layout;
    if (next === 'catalog' || next === 'desk' || next === 'floor') {
      setLayout(next);
      if (next === 'floor') setOverviewMode('cards');
      if (next === 'catalog') setOverviewMode('list');
      setAppliedDefaultLayout(true);
    }
  }, [appliedDefaultLayout, data?.monitor_prefs?.default_layout, focusAgentId]);

  const agents = data?.agents?.length ? data.agents : AGENT_FALLBACK_ROSTER;
  const selected = agents.find((a) => a.id === selectedId) ?? agents[0] ?? null;
  const liveCount = useMemo(() => agents.filter(isLiveAgent).length, [agents]);
  const alertCount = useMemo(() => agents.filter(isAlertAgent).length, [agents]);

  const pickRosterFilter = (key: 'all' | 'live' | 'alert') => {
    setFilter(key);
  };

  const grouped = useMemo(() => {
    const matches = (a: RoleAgent) => {
      if (filter === 'live' && !isLiveAgent(a)) return false;
      if (filter === 'alert' && !isAlertAgent(a)) return false;
      if (categoryFilter !== 'all' && a.category !== categoryFilter) return false;
      if (rosterFilter === 'custom' && !a.is_custom) return false;
      if (rosterFilter === 'disabled' && a.enabled !== false) return false;
      if (rosterFilter === 'oncall' && !a.on_call) return false;
      if (data?.monitor_prefs?.show_on_call_only && !a.on_call) return false;
      const minLv = data?.monitor_prefs?.filter_min_level ?? 0;
      const maxLv = data?.monitor_prefs?.filter_max_level ?? 4;
      if (a.level < minLv || a.level > maxLv) return false;
      if (data?.monitor_prefs?.show_disabled === false && a.enabled === false) return false;
      if (data?.monitor_prefs?.show_idle === false && a.status === 'idle') return false;
      if (data?.monitor_prefs?.show_custom_only && !a.is_custom) return false;
      const q = query.trim().toLowerCase();
      if (q) {
        const hay = `${a.name} ${a.id} ${a.category} ${a.responsibilities.join(' ')} ${a.system_prompt ?? ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    };
    const rank = (list: RoleAgent[]) => {
      const key = data?.monitor_prefs?.sort_by || 'level';
      return [...list].sort((a, b) => {
        if (key === 'name') return a.name.localeCompare(b.name, 'zh-Hant');
        if (key === 'status') {
          const order: Record<string, number> = { busy: 0, error: 1, waiting: 2, idle: 3, disabled: 4 };
          return (order[a.status] ?? 9) - (order[b.status] ?? 9);
        }
        if (key === 'cost') return (b.cost_usd || 0) - (a.cost_usd || 0);
        if (key === 'queue') return agentOpenCount(b) - agentOpenCount(a);
        const pins = data?.monitor_prefs?.pin_role_ids ?? [];
        const pinA = pins.indexOf(a.id);
        const pinB = pins.indexOf(b.id);
        if (pinA >= 0 || pinB >= 0) {
          if (pinA < 0) return 1;
          if (pinB < 0) return -1;
          return pinA - pinB;
        }
        return a.id.localeCompare(b.id);
      });
    };
    if (data?.monitor_prefs?.group_by === 'category') {
      const cats = data?.catalog_meta?.categories?.length
        ? data.catalog_meta.categories
        : Object.entries(CATEGORY_LABEL).map(([id, label]) => ({ id, label }));
      return cats
        .map((c, idx) => ({
          level: idx,
          label: c.label,
          agents: rank(agents.filter((a) => a.category === c.id && matches(a))),
        }))
        .filter((g) => g.agents.length > 0);
    }
    const levels = data?.levels?.length
      ? data.levels
      : [
          { level: 0, label: '最高決策層' },
          { level: 1, label: '技術領導層' },
          { level: 2, label: '領域領導層' },
          { level: 3, label: '執行層' },
          { level: 4, label: '支援角色' },
        ];
    return levels
      .map((lv) => ({
        ...lv,
        agents: rank(agents.filter((a) => a.level === lv.level && matches(a))),
      }))
      .filter((g) => g.agents.length > 0);
  }, [agents, categoryFilter, data?.catalog_meta, data?.levels, data?.monitor_prefs, filter, query, rosterFilter]);

  const visibleCount = useMemo(
    () => grouped.reduce((n, g) => n + g.agents.length, 0),
    [grouped],
  );

  const openDesk = (id: string, tab?: 'tasks' | 'monitor' | 'settings' | 'org') => {
    setSelectedId(id);
    onFocusAgent?.(id);
    setExpandedId(null);
    setLayout('desk');
    if (tab) setDeskTab(tab);
  };

  const browseLayout = layout !== 'desk';
  const statusMeta = selected ? AGENT_STATUS_META[selected.status] ?? AGENT_STATUS_META.idle : null;

  const visibleItems = useMemo(() => {
    if (!selected) return [];
    const filterDef = LIST_FILTERS.find((f) => f.key === itemFilter);
    let items = selected.work_items;
    if (filterDef?.statuses) {
      items = items.filter((i) => filterDef.statuses!.includes(i.status));
    } else if (itemFilter === 'assigned') {
      items = items.filter((i) => i.kind === 'assigned');
    } else if (itemFilter === 'review') {
      items = items.filter((i) => i.kind === 'review' || i.status === 'in_review');
    }
    return items;
  }, [itemFilter, selected]);

  const inboxReview = selected?.inbox.in_review ?? 0;
  const now = selected ? currentItem(selected) : null;
  const reports = selected?.direct_reports ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas text-[#f7f8f8]">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-white/[0.08] px-4 py-2.5">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">
            {layout === 'desk' && selected ? selected.name : `角色總覽 · ${agents.length}`}
          </h2>
          <p className="mt-0.5 text-[11px] text-[#8E8E93]">
            {layout === 'desk' && selected
              ? `左側名冊切換角色 · ${statusMeta?.label ?? ''} · L${selected.level}`
              : '點角色進入工作台；左側可持續切換'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-0.5">
            <button
              type="button"
              onClick={() => setLayout('desk')}
              className={`rounded px-2 py-1 text-[11px] ${
                layout === 'desk' ? 'bg-[#007AFF]/20 text-[#64D2FF]' : 'text-[#8a8f98]'
              }`}
            >
              工作台
            </button>
            <button
              type="button"
              onClick={() => {
                setLayout(overviewMode === 'cards' ? 'floor' : 'catalog');
              }}
              className={`rounded px-2 py-1 text-[11px] ${
                browseLayout ? 'bg-[#007AFF]/20 text-[#64D2FF]' : 'text-[#8a8f98]'
              }`}
            >
              總覽
            </button>
          </div>
          {browseLayout && (
            <>
              <div className="flex rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-0.5">
                <button
                  type="button"
                  onClick={() => {
                    setOverviewMode('list');
                    setLayout('catalog');
                  }}
                  className={`rounded px-2 py-1 text-[11px] ${
                    overviewMode === 'list' ? 'bg-white/[0.08] text-[#F5F5F7]' : 'text-[#8a8f98]'
                  }`}
                >
                  列表
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setOverviewMode('cards');
                    setLayout('floor');
                  }}
                  className={`rounded px-2 py-1 text-[11px] ${
                    overviewMode === 'cards' ? 'bg-white/[0.08] text-[#F5F5F7]' : 'text-[#8a8f98]'
                  }`}
                >
                  卡片
                </button>
              </div>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜尋角色／職責／提示詞"
                className="w-40 rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#f7f8f8]"
              />
            </>
          )}
          <button
            type="button"
            onClick={() => {
              setCloneFrom(null);
              setCreating(true);
            }}
            className="rounded-md border border-[#007AFF]/40 bg-[#007AFF]/15 px-2 py-1 text-[11px] text-[#64D2FF]"
          >
            新增角色
          </button>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
          >
            重新整理
          </button>
        </div>
      </div>

      {error && (
        <div className="mx-4 mt-3 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {error} · 已顯示角色目錄，後端恢復後會自動帶入任務
        </div>
      )}

      {browseLayout && (
        <div className="shrink-0 border-b border-white/[0.06] px-4 py-2.5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-xl bg-white/[0.04] p-0.5" role="tablist" aria-label="角色狀態篩選">
                {(
                  [
                    {
                      key: 'all' as const,
                      label: '全部',
                      count: agents.length,
                      title: '顯示全部角色',
                      disabled: false,
                    },
                    {
                      key: 'live' as const,
                      label: '活躍',
                      count: liveCount,
                      title: '只看執行中或等待中的角色',
                      disabled: false,
                    },
                    {
                      key: 'alert' as const,
                      label: '告警',
                      count: alertCount,
                      title: '只看告警、錯誤或超預算',
                      disabled: false,
                    },
                  ] as const
                ).map((tab) => {
                  const active = filter === tab.key;
                  return (
                    <button
                      key={tab.key}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      aria-disabled={tab.disabled}
                      title={tab.title}
                      disabled={tab.disabled}
                      onClick={() => pickRosterFilter(tab.key)}
                      className={`flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-[11px] leading-none ${
                        active
                          ? tab.key === 'alert'
                            ? 'bg-[#FF453A]/15 font-medium text-[#FF453A] shadow-sm'
                            : tab.key === 'live'
                              ? 'bg-[#30D158]/15 font-medium text-[#30D158] shadow-sm'
                              : 'bg-white/[0.1] font-medium text-[#F5F5F7] shadow-sm'
                          : tab.disabled
                            ? 'cursor-not-allowed text-[#48484A]'
                            : 'text-[#8E8E93] hover:text-[#F5F5F7]'
                      }`}
                    >
                      {tab.label}
                      <span className={`apple-data text-[10px] ${tab.disabled ? 'opacity-40' : ''}`}>{tab.count}</span>
                    </button>
                  );
                })}
              </div>
              {(filter !== 'all' || query.trim()) && (
                <button
                  type="button"
                  onClick={() => {
                    setFilter('all');
                    setQuery('');
                  }}
                  className="rounded-lg px-2 py-1 text-[11px] text-[#64D2FF] hover:bg-white/[0.06]"
                >
                  清除篩選
                </button>
              )}
            </div>
            <p className="text-[11px] text-[#8E8E93]">
              左側點層級或角色即可跳到此處
            </p>
          </div>
          <p className="mt-2 text-[11px] text-[#8E8E93]" aria-live="polite">
            {filter === 'live'
              ? `目前顯示 ${visibleCount} 席活躍角色（執行中或等待中）`
              : filter === 'alert'
                ? `目前顯示 ${visibleCount} 席告警角色`
                : `目前顯示 ${visibleCount} 席`}
            {query.trim() ? ` · 搜尋「${query.trim()}」` : ''}
          </p>
        </div>
      )}

      {layout === 'floor' && (
        <div ref={overviewScrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <div className="mb-3 text-[11px] text-[#8E8E93]">左側跳轉定位卡片；點卡片進入工作台。</div>
          {grouped.map((group) => (
            <section key={group.level} id={`role-level-${group.level}`} className="mb-5 scroll-mt-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#62666d]">
                {data?.monitor_prefs?.group_by === 'category' ? group.label : `L${group.level} ${group.label}`}
              </p>
              <div className="grid justify-start gap-3 [grid-template-columns:repeat(auto-fill,minmax(16.5rem,16.5rem))]">
                {group.agents.map((agent) => (
                  <AgentDeskCard
                    key={agent.id}
                    agent={agent}
                    highlighted={agent.id === selectedId}
                    compact={data?.monitor_prefs?.compact_cards === true}
                    showPrompt={data?.monitor_prefs?.show_prompt_preview !== false}
                    showCost={data?.monitor_prefs?.show_cost_in_cards !== false}
                    onOpen={() => openDesk(agent.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {layout === 'catalog' && (
        <div ref={overviewScrollRef} className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
          <div className="mb-3 text-[11px] text-[#8E8E93]">
            左側點角色會跳到此列表；點名稱進入工作台。
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
            >
              <option value="all">全部分類</option>
              {(data?.catalog_meta?.categories ?? Object.entries(CATEGORY_LABEL).map(([id, label]) => ({ id, label }))).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
            {(['all', 'custom', 'disabled', 'oncall'] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setRosterFilter(key)}
                className={`rounded px-2 py-1 text-[11px] ${
                  rosterFilter === key ? 'bg-[#007AFF]/20 text-[#64D2FF]' : 'text-[#8a8f98]'
                }`}
              >
                {key === 'all' ? '全部' : key === 'custom' ? '自定義' : key === 'disabled' ? '停用' : '值班'}
              </button>
            ))}
            <select
              value={data?.monitor_prefs?.sort_by || 'level'}
              onChange={(e) => void updateAgentMonitorPrefs({ sort_by: e.target.value }).then(() => refresh())}
              className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
            >
              <option value="level">依層級</option>
              <option value="name">依名稱</option>
              <option value="status">依狀態</option>
              <option value="cost">依花費</option>
              <option value="queue">依佇列</option>
            </select>
          </div>
          {grouped.map((group) => (
            <section key={`${group.level}-${group.label}`} id={`role-level-${group.level}`} className="mb-4 scroll-mt-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-[#62666d]">
                {data?.monitor_prefs?.group_by === 'category' ? group.label : `L${group.level} ${group.label}`}
                <span className="ml-2 font-mono">{group.agents.length}</span>
              </p>
              <div className="overflow-hidden rounded-lg border border-white/[0.08]">
                {group.agents.map((agent) => {
                  const meta = AGENT_STATUS_META[agent.status] ?? AGENT_STATUS_META.idle;
                  const open = agentOpenCount(agent);
                  return (
                    <div
                      key={agent.id}
                      id={`role-card-${agent.id}`}
                      className={`grid grid-cols-1 items-center gap-2 border-b border-white/[0.08] px-3 py-2 last:border-0 lg:grid-cols-[minmax(0,1fr)_7rem_8.5rem_auto] ${
                        agent.id === selectedId
                          ? 'bg-[#007AFF]/10'
                          : data?.monitor_prefs?.highlight_alerts !== false && (agent.alerts?.length ?? 0) > 0
                            ? 'bg-amber-500/5'
                            : 'bg-[#1C1C1E]'
                      }`}
                    >
                      <button type="button" className="min-w-0 text-left" onClick={() => openDesk(agent.id)}>
                        <p className="flex items-center gap-2 text-[13px] text-[#f7f8f8]">
                          <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
                          {agent.name}
                          {agent.is_custom ? <span className="text-[10px] text-[#64D2FF]">自定</span> : null}
                          {agent.enabled === false ? <span className="text-[10px] text-red-300">停用</span> : null}
                          {agent.on_call ? <span className="text-[10px] text-amber-200">值班</span> : null}
                          {agent.require_human_approval ? <span className="text-[10px] text-[#8a8f98]">需核准</span> : null}
                          {agent.mainland_only ? <span className="text-[10px] text-[#8a8f98]">僅國內</span> : null}
                        </p>
                        <p className="mt-0.5 line-clamp-2 text-[11px] text-[#8a8f98]">
                          {agent.description || agent.responsibilities[0] || agent.system_prompt || '尚無角色設定摘要'}
                        </p>
                      </button>
                      <div className="w-28 shrink-0 text-[10px] text-[#8a8f98]">
                        <p>{CATEGORY_LABEL[agent.category] ?? agent.category}</p>
                        <p className="font-mono">{agent.preferred_model || (TIER_LABEL[agent.default_tier] ?? agent.default_tier)}</p>
                      </div>
                      <div className="w-36 shrink-0 text-right">
                        {(agent.cost_usd ?? 0) > 0 ? (
                          <>
                            <p className="font-mono text-[11px] text-amber-300/90">{fmtUsd(agent.cost_usd)}</p>
                            <p className="text-[9px] text-[#62666d]">
                              API {fmtUsd(agent.api_cost_usd ?? 0)} · D {fmtUsd(agent.docker_cost_usd ?? 0)} · 阿里{' '}
                              {fmtUsd(agent.aliyun_cost_usd ?? 0)}
                            </p>
                          </>
                        ) : (
                          <p className="text-[10px] text-[#62666d]">尚無花費</p>
                        )}
                        <p className="mt-0.5 text-[10px] text-[#8a8f98]">{open} 開放</p>
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <button
                          type="button"
                          className="rounded border border-white/[0.08] px-2 py-1 text-[10px] text-[#8a8f98]"
                          onClick={() => {
                            openDesk(agent.id);
                            setDeskTab('settings');
                          }}
                        >
                          角色設定
                        </button>
                        <button
                          type="button"
                          className="rounded border border-white/[0.08] px-2 py-1 text-[10px] text-[#8a8f98]"
                          onClick={() => {
                            openDesk(agent.id);
                            setDeskTab('monitor');
                          }}
                        >
                          監控
                        </button>
                        <button
                          type="button"
                          className="rounded border border-white/[0.08] px-2 py-1 text-[10px] text-[#8a8f98]"
                          onClick={() => {
                            const pins = data?.monitor_prefs?.pin_role_ids ?? [];
                            const next = pins.includes(agent.id)
                              ? pins.filter((id) => id !== agent.id)
                              : [...pins, agent.id];
                            void updateAgentMonitorPrefs({ pin_role_ids: next }).then(() => refresh());
                          }}
                        >
                          {(data?.monitor_prefs?.pin_role_ids ?? []).includes(agent.id) ? '取消釘選' : '釘選'}
                        </button>
                        <button
                          type="button"
                          className="rounded border border-white/[0.08] px-2 py-1 text-[10px] text-[#8a8f98]"
                          onClick={() => void updateAgentSettings(agent.id, { enabled: agent.enabled === false }).then(() => refresh())}
                        >
                          {agent.enabled === false ? '啟用' : '停用'}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}

      {layout === 'desk' && selected && (
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* 角色名冊統一在左側 SidePanel；此處僅保留工作台內容 */}
          <section className="flex min-w-0 flex-1 flex-col overflow-hidden">
            <div className="shrink-0 border-b border-white/[0.08] px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${(AGENT_STATUS_META[selected.status] ?? AGENT_STATUS_META.idle).dot}`} />
                    <h3 className="text-base font-semibold">{selected.name}</h3>
                    <span className={`text-[11px] ${(AGENT_STATUS_META[selected.status] ?? AGENT_STATUS_META.idle).text}`}>
                      {(AGENT_STATUS_META[selected.status] ?? AGENT_STATUS_META.idle).label}
                    </span>
                    <select
                      value={selected.id}
                      onChange={(e) => openDesk(e.target.value)}
                      className="max-w-[180px] rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-0.5 text-[11px] text-[#d0d6e0]"
                      title="快速切換（完整名冊在左側）"
                    >
                      {agents.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <p className="mt-1 truncate text-[11px] text-[#8a8f98]">
                    L{selected.level} {selected.level_label}
                    {selected.is_custom ? ' · 自定義' : ' · 內建'}
                    {selected.enabled === false ? ' · 停用' : ''}
                    {selected.on_call ? ' · 值班' : ''}
                    {selected.reporting_to ? ` · 匯報 ${roleLabel(selected.reporting_to)}` : ''}
                    {' · '}佇列 {selected.queue} · 執行 {selected.executing} · 審查 {inboxReview}
                    {' · '}
                    {selected.preferred_model || (TIER_LABEL[selected.default_tier] ?? selected.default_tier)}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    type="button"
                    className="rounded-lg border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#F5F5F7]"
                    onClick={() => void updateAgentSettings(selected.id, { enabled: selected.enabled === false }).then(() => refresh())}
                  >
                    {selected.enabled === false ? '啟用' : '停用'}
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#F5F5F7]"
                    onClick={() => {
                      setCloneFrom(selected);
                      setCreating(true);
                    }}
                  >
                    複製
                  </button>
                  <p className="font-mono text-[11px] text-[#62666d]">最近 {fmtWhen(selected.last_activity_at)}</p>
                </div>
              </div>

              {(selected.alerts?.length ?? 0) > 0 && (
                <div className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[11px] text-amber-100">
                  {selected.alerts![0].level} · {selected.alerts![0].message}
                  {(selected.alerts!.length ?? 0) > 1 ? ` · 另 ${selected.alerts!.length - 1} 則` : ''}
                </div>
              )}

              <div className="mt-3 flex gap-1">
                {([
                  ['tasks', `任務 ${agentOpenCount(selected)}`],
                  ['monitor', '監控'],
                  ['settings', '設定'],
                  ['org', '組織'],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setDeskTab(key)}
                    className={`rounded-lg px-2.5 py-1 text-[12px] ${
                      deskTab === key ? 'bg-[#007AFF]/20 text-[#64D2FF]' : 'text-[#8a8f98] hover:text-[#d0d6e0]'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {deskTab === 'settings' && (
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <RoleSettingsPanel
                  agent={selected}
                  catalog={data?.catalog_meta}
                  agents={agents}
                  saving={saving}
                  error={saveError}
                  onClone={() => {
                    setCloneFrom(selected);
                    setCreating(true);
                  }}
                  onSave={async (draft: RoleSettingsDraft) => {
                    setSaving(true);
                    setSaveError(null);
                    try {
                      await updateAgentSettings(selected.id, draftToPayload(draft));
                      await refresh();
                    } catch (err) {
                      setSaveError((err as Error).message);
                    } finally {
                      setSaving(false);
                    }
                  }}
                  onReset={
                    selected.is_custom
                      ? undefined
                      : async () => {
                          setSaving(true);
                          setSaveError(null);
                          try {
                            await resetAgentSettings(selected.id);
                            await refresh();
                          } catch (err) {
                            setSaveError((err as Error).message);
                          } finally {
                            setSaving(false);
                          }
                        }
                  }
                  onDelete={
                    selected.is_custom
                      ? async () => {
                          if (!window.confirm(`確定刪除「${selected.name}」？`)) return;
                          setSaving(true);
                          setSaveError(null);
                          try {
                            await deleteCustomAgent(selected.id);
                            setSelectedId('manager');
                            await refresh();
                          } catch (err) {
                            setSaveError((err as Error).message);
                          } finally {
                            setSaving(false);
                          }
                        }
                      : undefined
                  }
                />
              </div>
            )}
            {deskTab === 'org' && (
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <div className="space-y-3">
                  <div className="apple-card apple-card--tight !p-0 px-3 py-2">
                    <p className="text-[10px] uppercase tracking-wider text-[#62666d]">匯報對象</p>
                    {selected.reporting_to ? (
                      <RoleChips ids={[selected.reporting_to]} onOpen={openDesk} />
                    ) : (
                      <p className="text-[11px] text-[#8a8f98]">無上級（決策層）</p>
                    )}
                  </div>
                  <div className="apple-card apple-card--tight !p-0 px-3 py-2">
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-[#62666d]">直屬下級 · {reports.length}</p>
                    <RoleChips ids={reports} onOpen={openDesk} />
                  </div>
                  <div className="apple-card apple-card--tight !p-0 px-3 py-2">
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-[#62666d]">可委派 · {selected.can_delegate_to.length}</p>
                    <RoleChips ids={selected.can_delegate_to} onOpen={openDesk} />
                  </div>
                  <div className="apple-card apple-card--tight !p-0 px-3 py-2">
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-[#62666d]">組織模板</p>
                    {(data?.catalog_meta?.org_templates ?? []).map((tpl) => (
                      <p key={tpl.id} className="text-[11px] text-[#d0d6e0]">
                        {tpl.name} · {tpl.role_count} 角色 · {tpl.description}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {deskTab === 'monitor' && (
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <RoleDeepMonitor agent={selected} />
                <div className="mt-4">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">角色監控</p>
                  <RoleMonitorExtras agent={selected} />
                </div>
                <div className="mt-4 apple-card apple-card--tight !p-0 px-3 py-2">
                  <p className="text-[10px] uppercase tracking-wider text-[#62666d]">監控偏好</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() => void updateAgentMonitorPrefs({ poll_interval_ms: pollMs === 5000 ? 8000 : 5000 }).then(() => refresh())}
                    >
                      輪詢 {pollMs / 1000}s
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({ show_idle: !(data?.monitor_prefs?.show_idle ?? true) }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.show_idle === false ? '顯示待命' : '隱藏待命'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({ show_disabled: !(data?.monitor_prefs?.show_disabled ?? true) }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.show_disabled === false ? '顯示停用' : '隱藏停用'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          show_custom_only: !(data?.monitor_prefs?.show_custom_only ?? false),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.show_custom_only ? '顯示全部角色' : '僅自定義'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          group_by: data?.monitor_prefs?.group_by === 'category' ? 'level' : 'category',
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.group_by === 'category' ? '依層級分組' : '依分類分組'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({ compact_cards: !(data?.monitor_prefs?.compact_cards ?? false) }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.compact_cards ? '一般卡片' : '緊湊卡片'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          show_prompt_preview: !(data?.monitor_prefs?.show_prompt_preview ?? true),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.show_prompt_preview === false ? '顯示角色設定摘要' : '隱藏角色設定摘要'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          highlight_alerts: !(data?.monitor_prefs?.highlight_alerts ?? true),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.highlight_alerts === false ? '突顯告警' : '取消突顯告警'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          auto_open_busy: !(data?.monitor_prefs?.auto_open_busy ?? false),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.auto_open_busy ? '關閉自動切入忙碌' : '忙碌時自動切入'}
                    </button>
                    <select
                      value={data?.monitor_prefs?.sort_by || 'level'}
                      onChange={(e) => void updateAgentMonitorPrefs({ sort_by: e.target.value }).then(() => refresh())}
                      className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
                    >
                      <option value="level">排序：層級</option>
                      <option value="name">排序：名稱</option>
                      <option value="status">排序：狀態</option>
                      <option value="cost">排序：花費</option>
                      <option value="queue">排序：佇列</option>
                    </select>
                    <select
                      value={data?.monitor_prefs?.default_layout || 'desk'}
                      onChange={(e) => void updateAgentMonitorPrefs({ default_layout: e.target.value }).then(() => refresh())}
                      className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
                    >
                      <option value="desk">預設視圖：工作台（名冊在左側）</option>
                      <option value="catalog">預設視圖：輔助目錄</option>
                      <option value="floor">預設視圖：樓層卡片</option>
                    </select>
                    <select
                      value={data?.monitor_prefs?.default_desk_tab || 'tasks'}
                      onChange={(e) => void updateAgentMonitorPrefs({ default_desk_tab: e.target.value }).then(() => refresh())}
                      className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
                    >
                      <option value="tasks">預設分頁：任務</option>
                      <option value="monitor">預設分頁：監控</option>
                      <option value="settings">預設分頁：角色設定</option>
                      <option value="org">預設分頁：組織</option>
                    </select>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          show_on_call_only: !(data?.monitor_prefs?.show_on_call_only ?? false),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.show_on_call_only ? '顯示全部席位' : '僅值班席'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          sound_on_alert: !(data?.monitor_prefs?.sound_on_alert ?? false),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.sound_on_alert ? '關閉告警音' : '開啟告警音'}
                    </button>
                    <button
                      type="button"
                      className="rounded border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]"
                      onClick={() =>
                        void updateAgentMonitorPrefs({
                          show_cost_in_cards: !(data?.monitor_prefs?.show_cost_in_cards ?? true),
                        }).then(() => refresh())
                      }
                    >
                      {data?.monitor_prefs?.show_cost_in_cards === false ? '卡片顯示花費' : '卡片隱藏花費'}
                    </button>
                    <select
                      value={String(data?.monitor_prefs?.filter_min_level ?? 0)}
                      onChange={(e) => void updateAgentMonitorPrefs({ filter_min_level: Number(e.target.value) }).then(() => refresh())}
                      className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
                    >
                      <option value="0">最低層 L0</option>
                      <option value="1">最低層 L1</option>
                      <option value="2">最低層 L2</option>
                      <option value="3">最低層 L3</option>
                      <option value="4">最低層 L4</option>
                    </select>
                    <select
                      value={String(data?.monitor_prefs?.filter_max_level ?? 4)}
                      onChange={(e) => void updateAgentMonitorPrefs({ filter_max_level: Number(e.target.value) }).then(() => refresh())}
                      className="rounded border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#d0d6e0]"
                    >
                      <option value="0">最高層 L0</option>
                      <option value="1">最高層 L1</option>
                      <option value="2">最高層 L2</option>
                      <option value="3">最高層 L3</option>
                      <option value="4">最高層 L4</option>
                    </select>
                  </div>
                </div>
              </div>
            )}
            {deskTab === 'tasks' && (
            <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)_minmax(260px,0.75fr)]">
              <div className="flex min-h-0 flex-col overflow-hidden border-b border-white/[0.08] xl:border-b-0 xl:border-r">
                <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 px-4 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[#62666d]">
                    任務列表 · {visibleItems.length}/{selected.work_items.length}
                  </p>
                  <div className="flex flex-wrap items-center gap-1">
                    {LIST_FILTERS.map((f) => (
                      <button
                        key={f.key}
                        type="button"
                        onClick={() => setItemFilter(f.key)}
                        className={`rounded px-2 py-0.5 text-[10px] ${
                          itemFilter === f.key
                            ? 'bg-[#007AFF]/20 text-[#64D2FF]'
                            : 'text-[#8a8f98] hover:text-[#d0d6e0]'
                        }`}
                      >
                        {f.label}
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => setBoardMode((v) => (v === 'list' ? 'kanban' : 'list'))}
                      className="ml-1 rounded border border-white/[0.08] px-2 py-0.5 text-[10px] text-[#8a8f98]"
                    >
                      {boardMode === 'list' ? '看板' : '列表'}
                    </button>
                  </div>
                </div>

                <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
                  {boardMode === 'list' ? (
                    visibleItems.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-white/[0.08] px-4 py-10 text-center">
                        <p className="text-[13px] text-[#d0d6e0]">尚無{itemFilter === 'all' ? '' : '符合條件的'}工作項</p>
                        <p className="mt-1 text-[11px] text-[#62666d]">
                          此 Agent 待命。公司任務分解後，指派給「{selected.name}」的工作會出現在此列表。
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-1.5">
                        {visibleItems.map((item) => (
                          <WorkItemCard
                            key={`${item.task_id}-${item.id}-${item.kind}`}
                            item={item}
                            expanded={expandedId === `${item.task_id}-${item.id}-${item.kind}`}
                            onToggle={() =>
                              setExpandedId((cur) => {
                                const key = `${item.task_id}-${item.id}-${item.kind}`;
                                return cur === key ? null : key;
                              })
                            }
                          />
                        ))}
                      </div>
                    )
                  ) : (
                    <div className="grid min-h-[220px] grid-cols-1 gap-2 md:grid-cols-2 2xl:grid-cols-4">
                      {KANBAN.map((col) => {
                        const list = visibleItems.filter((i) => col.statuses.includes(i.status));
                        return (
                          <div key={col.key} className="flex min-h-0 flex-col rounded-lg border border-white/[0.08] bg-[#0a0b0c] p-2">
                            <p className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-[#62666d]">
                              {col.label}
                              <span className="font-mono">{list.length}</span>
                            </p>
                            <div className="space-y-1.5">
                              {list.length === 0 ? (
                                <p className="py-6 text-center text-[11px] text-[#62666d]">空</p>
                              ) : (
                                list.map((item) => (
                                  <WorkItemCard
                                    key={`${item.task_id}-${item.id}-${item.kind}`}
                                    item={item}
                                    compact
                                    expanded={expandedId === `${item.task_id}-${item.id}-${item.kind}`}
                                    onToggle={() =>
                                      setExpandedId((cur) => {
                                        const key = `${item.task_id}-${item.id}-${item.kind}`;
                                        return cur === key ? null : key;
                                      })
                                    }
                                  />
                                ))
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>

              <div className="min-h-0 space-y-3 overflow-y-auto border-b border-white/[0.08] p-3 xl:border-b-0 xl:border-r">
                {now && (
                  <div className="rounded-xl border border-[#007AFF]/30 bg-[#007AFF]/10 px-3 py-2.5">
                    <p className="text-[10px] uppercase tracking-wider text-[#64D2FF]">目前任務 · 即時</p>
                    <p className="mt-0.5 text-[13px] text-[#f7f8f8]">{now.title}</p>
                    <p className="text-[11px] text-[#8a8f98]">{now.task_query || now.task_id}</p>
                    {now.description && (
                      <p className="mt-1 text-[11px] leading-relaxed text-[#d0d6e0]">{now.description}</p>
                    )}
                  </div>
                )}

                <CardSection title="即時效能" hint="輪詢同步">
                  <div className="grid grid-cols-2 gap-2">
                    <Kpi
                      label="平均延遲"
                      value={`${Math.round(selected.metrics?.avg_latency_ms ?? 0)} ms`}
                      accent="blue"
                    />
                    <Kpi
                      label="P95"
                      value={`${Math.round(selected.metrics?.p95_latency_ms ?? 0)} ms`}
                    />
                    <Kpi
                      label="成功率"
                      value={`${selected.metrics?.success_rate ?? 0}%`}
                      accent="green"
                    />
                    <Kpi
                      label="容量"
                      value={`${selected.metrics?.capacity_pct ?? 0}%`}
                      hint={`${selected.capacity_used ?? selected.executing}/${selected.max_parallel_work}`}
                    />
                    <Kpi label="Token in/out" value={`${selected.metrics?.tokens_in ?? 0}/${selected.metrics?.tokens_out ?? 0}`} />
                    <Kpi
                      label="SLA 逾時"
                      value={String(selected.metrics?.sla_breaches ?? 0)}
                      accent={(selected.metrics?.sla_breaches ?? 0) > 0 ? 'red' : undefined}
                    />
                  </div>
                </CardSection>

                <CardSection title="預算快覽" hint="API＋Docker＋阿里雲">
                  <BudgetCostCards agent={selected} cols="grid-cols-2" />
                </CardSection>

                <CardSection title="角色監控">
                  <RoleMonitorExtras agent={selected} />
                </CardSection>

                {(selected.alerts?.length ?? 0) > 0 && (
                  <CardSection title="告警" className="border-amber-500/20 bg-amber-500/5">
                    {selected.alerts!.map((al, i) => (
                      <p key={`${al.message}-${i}`} className="text-[11px] text-amber-100">
                        {al.level} · {al.message}
                      </p>
                    ))}
                  </CardSection>
                )}
              </div>

              <div className="min-h-0 space-y-3 overflow-y-auto p-3">
                {(selected.company_tasks?.length ?? 0) > 0 && (
                  <CardSection title="經手公司任務">
                    <div className="space-y-1">
                      {(selected.company_tasks ?? []).map((t) => (
                        <div key={t.task_id} className="flex items-center justify-between gap-2 py-1">
                          <span className="min-w-0 truncate text-[11px] text-[#d0d6e0]">{t.query}</span>
                          <span className="shrink-0 font-mono text-[10px] text-[#8a8f98]">{t.status || t.phase}</span>
                        </div>
                      ))}
                    </div>
                  </CardSection>
                )}

                <CardSection title={`事件時間軸 · ${selected.events.length}`}>
                  {selected.events.length === 0 ? (
                    <p className="py-2 text-center text-[11px] text-[#62666d]">尚無此角色事件</p>
                  ) : (
                    selected.events.map((ev, i) => (
                      <EventRow key={`${ev.ts}-${ev.event}-${i}`} event={ev} />
                    ))
                  )}
                </CardSection>

                <CardSection title="組織">
                  <div className="space-y-2">
                    <div>
                      <p className="text-[10px] text-[#62666d]">匯報對象</p>
                      {selected.reporting_to ? (
                        <RoleChips ids={[selected.reporting_to]} onOpen={openDesk} />
                      ) : (
                        <p className="text-[11px] text-[#8a8f98]">無上級（決策層）</p>
                      )}
                    </div>
                    <div>
                      <p className="text-[10px] text-[#62666d]">直屬下級</p>
                      <RoleChips ids={reports} onOpen={openDesk} />
                    </div>
                    {selected.can_delegate_to.length > 0 && (
                      <div>
                        <p className="text-[10px] text-[#62666d]">可委派</p>
                        <RoleChips ids={selected.can_delegate_to} onOpen={openDesk} />
                      </div>
                    )}
                  </div>
                </CardSection>

                <CardSection title="職責 / 角色設定">
                  <ul className="space-y-1.5">
                    {selected.responsibilities.map((line) => (
                      <li key={line} className="text-[11px] leading-relaxed text-[#d0d6e0]">
                        {line}
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="mt-2 text-[11px] text-[#64D2FF]"
                    onClick={() => setDeskTab('settings')}
                  >
                    編輯完整角色設定
                  </button>
                </CardSection>
              </div>
            </div>
            )}
          </section>
        </div>
      )}
      {creating && (
        <CreateRoleModal
          catalog={data?.catalog_meta}
          agents={agents}
          cloneFrom={cloneFrom}
          onClose={() => {
            setCreating(false);
            setCloneFrom(null);
          }}
          onCreate={async (payload) => {
            const created = await createCustomAgent(payload);
            await refresh();
            openDesk(created.id);
            setDeskTab('settings');
          }}
        />
      )}
    </div>
  );
}
