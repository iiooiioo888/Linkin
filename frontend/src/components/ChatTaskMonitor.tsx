/**
 * 對話右側監控欄：僅在進行中任務掛載。
 * 角色啟用／審計門票／AI 計費／Docker 計費。
 */
import { useMemo } from 'react';
import type { RahoPendingDecision, TaskProgress } from '../types';
import { useMonitorHub } from '../hooks/useMonitorHub';
import { useMonitorStore } from '../stores/monitorStore';
import { AGENT_STATUS_META } from '../lib/agentUi';
import {
  flattenWsNodes,
  numBudget,
  wsColumnKey,
  wsTokens,
} from '../lib/chatWorkspace';
import { ticketOf } from './taskdetail/narrow';
import { DIMENSION_META, ticketStatusLabel } from './taskdetail/labels';
import { COMPANY_PHASES, OPC_PHASES, STANDARD_PHASES, roleLabel } from './TaskPanel';
import { MonitorSection } from './ChatMonitorCards';
import { L0BiasHint } from './L0BiasHint';
import IntegrationsStrip from './IntegrationsStrip';
import { formatDurationCompact, taskEta } from '../lib/taskTiming';
import { buttonEnabled, inferRuntimeState } from '../lib/taskStateMatrix';

interface ChatTaskMonitorProps {
  task: TaskProgress;
  pending: RahoPendingDecision[];
  running: boolean;
  now: number;
  onOpenTask?: () => void;
  onOpenTrace?: (taskId: string) => void;
  onOpenContext?: () => void;
  onPause?: () => void;
  onResume?: () => void;
}

function fmtUsd(n: number): string {
  if (!Number.isFinite(n)) return '$0.00';
  if (n < 0.01) return `$${n.toFixed(4)}`;
  if (n < 1) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

function scoreOf(raw: unknown): number | null {
  const n = typeof raw === 'number' ? raw : Number(raw);
  return Number.isFinite(n) ? n : null;
}

export default function ChatTaskMonitor({
  task,
  pending,
  running,
  now,
  onOpenTask,
  onOpenTrace,
  onOpenContext,
  onPause,
  onResume,
}: ChatTaskMonitorProps) {
  useMonitorHub(true);
  const agentsSnap = useMonitorStore((s) => s.agents);
  const billing = useMonitorStore((s) => s.billing);

  const nodes = useMemo(() => flattenWsNodes(task), [task]);
  const ticket = ticketOf(task);
  const phases =
    task.resolved_path === 'opc' ? OPC_PHASES : task.resolved_path === 'company' ? COMPANY_PHASES : STANDARD_PHASES;
  const phaseLabel = phases.find((p) => p.key === task.phase)?.label ?? (task.phase || '待命');
  const eta = taskEta(task, now);
  const tokens = wsTokens(task);
  const spent = numBudget(task, 'task_spent');
  const limit = numBudget(task, 'task_limit') || 2;
  const apiCost = numBudget(task, 'task_api_spent') || numBudget(task, 'api_cost');
  const model = String(task.budget?.active_tier || '').trim();
  const dockerTask = numBudget(task, 'docker_cost');

  const assigned = useMemo(() => {
    const ids = nodes.map((n) => String(n.item.assignee || '').trim()).filter(Boolean);
    return [...new Set(ids)];
  }, [nodes]);

  const roleRows = useMemo(() => {
    const roster = agentsSnap?.agents ?? [];
    const byId = new Map(roster.map((a) => [a.id, a]));
    const keys = assigned.length ? assigned : roster.filter((a) => a.status === 'busy' || a.status === 'waiting').map((a) => a.id);
    const seen = new Set<string>();
    return keys
      .filter((id) => {
        if (seen.has(id)) return false;
        seen.add(id);
        return true;
      })
      .map((id) => {
        const agent = byId.get(id);
        const live = nodes.filter((n) => n.item.assignee === id);
        const col = live[0] ? wsColumnKey(live[0].status) : 'queue';
        const status = agent?.status || (col === 'executing' ? 'busy' : live.length ? 'waiting' : 'idle');
        return {
          id,
          name: agent?.name || roleLabel(id),
          enabled: agent?.enabled !== false,
          status,
          items: live.length,
          api: agent?.api_cost_usd ?? 0,
        };
      });
  }, [agentsSnap?.agents, assigned, nodes]);

  const enabledN = roleRows.filter((r) => r.enabled).length;
  const docker = billing?.docker;
  const dockerUsd = docker?.total_now ?? billing?.breakdown?.docker_usd ?? dockerTask;
  const dockerRate = docker?.total_hourly_rate ?? 0;
  const dockerServices = (docker?.per_service ?? billing?.per_service ?? [])
    .filter((s) => (s.source || 'docker') !== 'aliyun')
    .slice(0, 4);
  const scores = ticket?.dimension_scores ?? {};
  const trail = Array.isArray(ticket?.audit_trail) ? ticket.audit_trail : [];
  const blockers = pending.filter((p) => !p.resolved);
  const runtimeState = inferRuntimeState({
    status: task.status,
    resumable: task.resumable,
    runtime_state: (task as { runtime_state?: string }).runtime_state,
    phase: task.phase,
  });
  const canPause = buttonEnabled(runtimeState, 'pause') && Boolean(onPause);
  const canResume = buttonEnabled(runtimeState, 'resume') && Boolean(onResume) && Boolean(task.resumable);
  const spentPct = limit > 0 ? Math.min(100, Math.round((spent / limit) * 100)) : 0;
  const primarySeat = roleRows.find((r) => r.status === 'busy') || roleRows[0];

  return (
    <aside className="ws-side" aria-label="任務監控" data-testid="chat-task-monitor">
      <div className="ws-side-h">
        <div>
          <p className="ws-side-k">任務監控</p>
          <p className="ws-side-t">{phaseLabel}</p>
        </div>
        <div className="ws-side-acts">
          {canPause && running && (
            <button type="button" className="ws-btn ws-btn-danger" onClick={onPause} data-matrix-action="pause">
              暫停
            </button>
          )}
          {canResume && !running && !blockers.length && (
            <button type="button" className="ws-btn ws-btn-primary" onClick={onResume} data-matrix-action="resume">
              續跑
            </button>
          )}
          {onOpenContext && (
            <button type="button" className="ws-btn" onClick={onOpenContext} title="開啟對話詳細區 Context">
              Context
            </button>
          )}
          {onOpenTrace && (
            <button type="button" className="ws-btn" onClick={() => onOpenTrace(task.task_id)}>
              軌跡
            </button>
          )}
          {onOpenTask && (
            <button type="button" className="ws-btn" onClick={onOpenTask}>
              詳情
            </button>
          )}
        </div>
      </div>

      <div className="ws-side-scroll">
        <div className="ws-side-kpi" data-testid="runtime-hud-compact">
          <div>
            <span>席位</span>
            <strong>{primarySeat?.name || '—'}</strong>
          </div>
          <div>
            <span>動作</span>
            <strong>{phaseLabel}</strong>
          </div>
          <div>
            <span>預算</span>
            <strong>{spentPct}%</strong>
          </div>
        </div>
        <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-white/10" title="任務預算進度">
          <i className="block h-full rounded-full bg-[#0A84FF]" style={{ width: `${spentPct}%` }} />
        </div>
        <p className="mb-2 text-[10px] text-[#636366]">
          狀態 {runtimeState} · 耗時 {eta ? formatDurationCompact(eta.elapsedSec) : '—'}
        </p>

        <MonitorSection title="啟用角色" hint={`${enabledN}/${roleRows.length || 0}`} defaultCollapsed>
          {roleRows.length === 0 ? (
            <p className="ws-empty">任務啟動後會列出被指派的角色</p>
          ) : (
            <ul className="ws-role-list">
              {roleRows.map((row) => {
                const meta = AGENT_STATUS_META[row.status] ?? AGENT_STATUS_META.idle;
                return (
                  <li key={row.id} className={`ws-role${row.enabled ? '' : ' is-off'}`}>
                    <span className={`rd-od ${row.status === 'busy' ? 'run' : row.enabled ? 'on' : 'off'}`} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[12px] font-medium text-[#F5F5F7]">{row.name}</p>
                      <p className={`truncate text-[10px] ${meta.text}`}>
                        {row.enabled ? meta.label : '停用'}
                        {row.items ? ` · ${row.items} 項` : ''}
                      </p>
                    </div>
                    {row.api > 0 && <span className="ws-role-cost">{fmtUsd(row.api)}</span>}
                  </li>
                );
              })}
            </ul>
          )}
        </MonitorSection>

        <MonitorSection title="外部整合" hint="召回／Agent／設計" defaultCollapsed>
          <IntegrationsStrip density="compact" showSummary={false} pollMs={15000} />
          <p className="mt-2 text-[10px] leading-relaxed text-[#636366]">
            MemOS／Viking／WeKnora 服務 L0 注入；Yao／Ouroboros／OpenPencil 為顯式動作。點晶片開啟面板。
          </p>
        </MonitorSection>

        <MonitorSection title="需求審計門票" hint={ticket ? ticketStatusLabel(ticket.status) : '尚無門票'} defaultCollapsed>
          <L0BiasHint snapshot={task.raho?.l0} compact />
          {blockers[0] && (
            <p className="mb-2 rounded-lg border border-[#FF9F0A]/30 bg-[#FF9F0A]/10 px-2.5 py-2 text-[11px] leading-relaxed text-[#FF9F0A]">
              待裁決：{blockers[0].question}
            </p>
          )}
          {ticket ? (
            <>
              {ticket.clarified_goal && typeof ticket.clarified_goal === 'object' && (
                <p className="mb-2 text-[11px] leading-relaxed text-[#AEAEB2]">
                  {String(
                    (ticket.clarified_goal as { core_action?: string }).core_action ||
                      (ticket.clarified_goal as { quantified_success?: string }).quantified_success ||
                      '',
                  )}
                </p>
              )}
              <div className="space-y-1.5">
                {DIMENSION_META.map((dim) => {
                  const n = scoreOf(scores[dim.key]);
                  if (n == null) return null;
                  return (
                    <div key={dim.key}>
                      <div className="mb-0.5 flex justify-between text-[10px] text-[#8E8E93]">
                        <span>{dim.label}</span>
                        <span>{Math.round(n)}</span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-white/10">
                        <i
                          className="block h-full rounded-full bg-[#0A84FF]"
                          style={{ width: `${Math.min(100, n)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
              {trail.length > 0 && (
                <ol className="mt-2 space-y-1 border-t border-white/[0.06] pt-2">
                  {trail.slice(-3).map((row, i) => (
                    <li key={`${i}-${row.slice(0, 12)}`} className="text-[10px] leading-relaxed text-[#8E8E93]">
                      {row}
                    </li>
                  ))}
                </ol>
              )}
            </>
          ) : (
            <p className="ws-empty">尚未核發需求審計門票</p>
          )}
        </MonitorSection>

        <MonitorSection title="AI 計費" hint={model || '模型用量'} defaultCollapsed>
          <div className="ws-bill-grid">
            <div>
              <span>Token</span>
              <strong>{tokens.toLocaleString()}</strong>
            </div>
            <div>
              <span>本任務</span>
              <strong>{fmtUsd(spent)}</strong>
            </div>
            <div>
              <span>模型費</span>
              <strong>{fmtUsd(apiCost)}</strong>
            </div>
            <div>
              <span>上限</span>
              <strong>{fmtUsd(limit)}</strong>
            </div>
          </div>
          {agentsSnap?.summary?.total_api_cost_usd != null && (
            <p className="mt-2 text-[10px] text-[#636366]">
              全員 API 累計 {fmtUsd(agentsSnap.summary.total_api_cost_usd)}
            </p>
          )}
        </MonitorSection>

        <MonitorSection
          title="Docker 計費"
          hint={dockerRate > 0 ? `${fmtUsd(dockerRate)}/h` : '容器按時'}
          defaultCollapsed
        >
          <div className="ws-bill-grid">
            <div>
              <span>目前</span>
              <strong>{fmtUsd(dockerUsd)}</strong>
            </div>
            <div>
              <span>本月估</span>
              <strong>{fmtUsd(docker?.month_projected ?? billing?.month_projected ?? 0)}</strong>
            </div>
          </div>
          {dockerServices.length > 0 ? (
            <ul className="mt-2 space-y-1">
              {dockerServices.map((s) => (
                <li key={`${s.source || 'docker'}-${s.service}`} className="flex justify-between gap-2 text-[11px]">
                  <span className="truncate text-[#AEAEB2]">{s.product_name || s.service}</span>
                  <span className="shrink-0 text-[#F5F5F7]">{fmtUsd(s.cost)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="ws-empty">尚無容器費用（Compose 未掛載時為 0）</p>
          )}
        </MonitorSection>
      </div>
    </aside>
  );
}
