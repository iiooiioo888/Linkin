/**
 * AgentsMonitorPanel — 每位公司角色一張獨立工作台。
 * 每位角色一張工作台：質詢鏈與任用合在同一視圖。
 * 角色名冊在左側 SidePanel；總覽是控制台「即時」，不在此頁重複。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createCustomAgent,
  deleteCustomAgent,
  fetchAgentMonitor,
  fetchRahoTree,
  resetAgentSettings,
  updateAgentMonitorPrefs,
  updateAgentSettings,
} from '../api/client';
import {
  CATEGORY_LABEL,
  JUMP_AGENT_EVENT,
  ROUTING_LABEL,
  TIER_LABEL,
  WORK_ITEM_COLUMNS,
  blankMetrics,
  consumePendingDeskTab,
  consumePendingGrillReveal,
  filterAgentsByDesk,
  fmtUsd,
  fmtWhen,
  isLinkinStudioAgent,
  isQuantDeskRole,
  itemsInColumn,
  pickDefaultAgentId,
  routeDisplayName,
  workItemColumnKey,
  type AgentDeskScope,
  type JumpAgentDetail,
  type WorkItemColumnKey,
} from '../lib/agentUi';
import { AGENT_FALLBACK_ROSTER } from '../lib/monitorFallbacks';
import { nodesForRole } from '../lib/rahoUi';
import type { AgentMonitorData, AgentWorkItem, GrillTree, L0Snapshot, RoleAgent } from '../types';
import GrillTreePanel from './GrillTreePanel';
import RoleSettingsPanel, { CreateRoleModal, draftToPayload, type RoleSettingsDraft } from './RoleSettingsPanel';
import { RdCell, RoleDeskHeader, RoleRightPanel, RoleStatsStrip, type RoleDeskTab } from './RoleDeskLayout';
import { StatusColumnBoard } from './StatusColumnBoard';
import StrategyCatalogPanel from './StrategyCatalogPanel';
import { ITEM_STATUS_META } from './TaskPanel';

function itemStatus(status: string): { label: string; cls: string } {
  return ITEM_STATUS_META[status] ?? { label: status, cls: 'bg-gray-700/60 text-gray-300' };
}

function toDeskTab(tab?: string | null): RoleDeskTab {
  if (tab === 'monitor' || tab === 'settings' || tab === 'quant') return tab;
  return 'tasks';
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
  const col = workItemColumnKey(item.status);
  const running = col === 'executing';
  const shortId = (item.task_id || item.id || '').replace(/^.*[#-]/, '').slice(-4) || item.id.slice(0, 4);
  return (
    <button type="button" onClick={onToggle} className={`rd-tc w-full ${expanded ? 'on' : ''}`}>
      <div className="rd-tc-t">
        <span className={`rd-od shrink-0 ${running ? 'run' : col === 'done' ? 'on' : 'off'}`} />
        <span className="rd-tc-ttl">{item.title}</span>
        <span className="rd-tc-id">#{shortId}</span>
      </div>
      {!compact ? (
        <p className="rd-tc-d">{item.task_query || item.description || item.task_id}</p>
      ) : null}
      <div className="rd-tc-m">
        <span className={`rd-badge ${running ? 'run' : ''} ${st.cls}`}>{st.label}</span>
        <span className="rd-tc-meta">{fmtWhen(item.updated_at)}</span>
        <span className="rd-tc-cost">{fmtUsd(item.cost_usd)}</span>
      </div>
      {expanded && (
        <div className="mt-2 space-y-1.5 border-t border-white/[0.08] pt-2">
          {item.description && <p className="text-[11px] leading-relaxed text-[#AEAEB2]">{item.description}</p>}
          {item.output_preview && (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-[#141416] px-2 py-1 font-mono text-[10px] text-[#AEAEB2]">
              {item.output_preview}
            </pre>
          )}
          {(item.depends_on?.length ?? 0) > 0 && (
            <p className="text-[10px] text-[#636366]">依賴 {item.depends_on!.join(', ')}</p>
          )}
        </div>
      )}
    </button>
  );
}

function ExtraGrid({ cells }: { cells: Array<{ label: string; value: string; color?: string }> }) {
  return (
    <div className="rd-grid2">
      {cells.map((c) => (
        <RdCell key={c.label} label={c.label} value={c.value} color={c.color} />
      ))}
    </div>
  );
}

function RoleMonitorExtras({ agent, onOpenQuant, onOpenGrill }: { agent: RoleAgent; onOpenQuant?: () => void; onOpenGrill?: () => void }) {
  const m = agent.metrics ?? blankMetrics();
  if (isQuantDeskRole(agent.id)) {
    return (
      <div className="space-y-2">
        <ExtraGrid
          cells={[
            { label: '工具呼叫', value: String(m.tool_calls) },
            { label: '可回測', value: '29' },
            { label: '策略目錄', value: '300+' },
            { label: '完成', value: String(agent.done) },
          ]}
        />
        <button type="button" className="rd-btn inline-flex text-[11px] text-[#0A84FF]" onClick={onOpenQuant}>
          開啟回測策略庫
        </button>
      </div>
    );
  }
  if (agent.id === 'constitutional_inspector') {
    return (
      <ExtraGrid
        cells={[
          { label: '簽核通過', value: String(m.review_pass) },
          { label: '退回重做', value: String(m.review_rework) },
          { label: '向上呈報', value: String(m.human_escalations) },
          { label: '線路', value: agent.raho_lane_label || '獨立審查' },
        ]}
      />
    );
  }
  if (agent.id === 'atomic_executor') {
    return (
      <div className="space-y-2">
        <ExtraGrid
          cells={[
            { label: '戰前質詢', value: String(m.grill_count) },
            { label: '被質詢率', value: `${Math.round((m.grill_rate ?? 0) * 100)}%` },
            { label: '重試', value: String(m.retries) },
            { label: '線路', value: agent.raho_lane_label || '指揮鏈' },
          ]}
        />
        <button type="button" className="rd-btn inline-flex text-[11px] text-[#0A84FF]" onClick={onOpenGrill}>
          查看質詢
        </button>
      </div>
    );
  }
  if (agent.id === 'tactical_commander') {
    return (
      <div className="space-y-2">
        <ExtraGrid
          cells={[
            { label: '被質詢', value: `${Math.round((m.grill_rate ?? 0) * 100)}%` },
            { label: '決策清晰', value: `${Math.round((m.decision_clarity ?? 1) * 100)}%` },
            { label: '上交用戶', value: String(m.human_escalations) },
            { label: '線路', value: agent.raho_lane_label || '指揮鏈' },
          ]}
        />
        <button type="button" className="rd-btn inline-flex text-[11px] text-[#0A84FF]" onClick={onOpenGrill}>
          查看質詢
        </button>
      </div>
    );
  }
  if (agent.id === 'requirement_auditor') {
    return (
      <div className="space-y-2">
        <ExtraGrid
          cells={[
            { label: '審計回合', value: String(m.grill_count) },
            { label: '鎖定清晰', value: `${Math.round((m.decision_clarity ?? 1) * 100)}%` },
            { label: '終止／失敗', value: String(m.errors) },
            { label: '線路', value: agent.raho_lane_label || '指揮鏈' },
          ]}
        />
        <button type="button" className="rd-btn inline-flex text-[11px] text-[#0A84FF]" onClick={onOpenGrill}>
          查看質詢
        </button>
      </div>
    );
  }
  if (agent.id === 'reviewer') {
    return (
      <ExtraGrid
        cells={[
          { label: '通過', value: String(m.review_pass) },
          { label: '退回', value: String(m.review_rework) },
          { label: '強制完成', value: String(m.review_force) },
        ]}
      />
    );
  }
  if (agent.id === 'manager') {
    return (
      <ExtraGrid
        cells={[
          { label: '協調任務', value: String(agent.company_tasks.length) },
          { label: '預算告警', value: String(m.budget_alerts) },
          { label: '被質詢率', value: `${Math.round((m.grill_rate ?? 0) * 100)}%` },
          { label: '決策清晰', value: `${Math.round((m.decision_clarity ?? 1) * 100)}%` },
          { label: 'RAHO 職級', value: m.demoted ? '已降級' : m.raho_rank === 'watch' ? '觀察' : '正常' },
        ]}
      />
    );
  }
  if (agent.id === 'synthesizer') {
    const outputs = agent.work_items.filter((i) => i.kind === 'synthesize' && i.output_preview);
    return (
      <div className="rd-cell">
        <div className="rd-cell-l">最近整合產出</div>
        {outputs.length === 0 ? (
          <p className="mt-1 text-[11px] text-[#636366]">尚無整合結果</p>
        ) : (
          outputs.slice(0, 2).map((item) => (
            <p key={`${item.task_id}-${item.id}`} className="mt-1 line-clamp-3 text-[11px] text-[#AEAEB2]">
              {item.output_preview}
            </p>
          ))
        )}
      </div>
    );
  }
  if (agent.id === 'coordinator') {
    return (
      <ExtraGrid
        cells={[
          { label: '阻塞項', value: String(agent.blocked) },
          { label: '工具呼叫', value: String(m.tool_calls) },
        ]}
      />
    );
  }
  return (
    <ExtraGrid
      cells={[
        { label: '工具呼叫', value: String(m.tool_calls) },
        { label: '錯誤', value: String(m.errors), color: m.errors ? 'var(--apple-red)' : 'var(--apple-green)' },
        { label: '被質詢', value: `${Math.round((m.grill_rate ?? 0) * 100)}%` },
        { label: '完成', value: String(agent.done) },
      ]}
    />
  );
}

function RoleDeepMonitor({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  return (
    <>
      <section className="rd-sec">
        <div className="rd-tt">模型與路由</div>
        <div className="rd-grid2">
          <RdCell label="指定模型" value={agent.preferred_model || (TIER_LABEL[agent.default_tier] ?? agent.default_tier)} />
          <RdCell label="路由" value={ROUTING_LABEL[agent.routing_strategy || ''] ?? (agent.routing_strategy || '品質')} />
          <RdCell label="故障轉移" value={String(agent.failover_models?.length ?? 0)} />
          <RdCell label="快取命中" value={String(m.cache_hits ?? 0)} />
          <RdCell label="允許工具" value={String(agent.tools_allowed?.length ?? 0)} />
          <RdCell label="人工升級" value={String(m.human_escalations ?? 0)} />
        </div>
      </section>
      <section className="rd-sec">
        <div className="rd-tt">角色與合規</div>
        <div className="rd-grid2">
          <RdCell label="狀態" value={agent.enabled === false ? '停用' : '啟用'} />
          <RdCell label="質詢層" value={agent.raho_label || '—'} />
          <RdCell label="線路" value={agent.raho_lane_label || '—'} />
          <RdCell label="分類" value={CATEGORY_LABEL[agent.category] ?? agent.category} />
          <RdCell label="語言" value={agent.language || 'zh-TW'} />
          <RdCell label="值班" value={agent.on_call ? 'On-call' : '否'} />
          <RdCell label="合規" value={agent.mainland_only ? '僅國內' : '全球'} />
          <RdCell label="日工作上限" value={agent.max_daily_items ? String(agent.max_daily_items) : '不限'} />
        </div>
      </section>
      {(agent.alerts?.length ?? 0) > 0 ? (
        <section className="rd-sec">
          <div className="rd-tt">角色告警</div>
          {agent.alerts!.map((al, i) => (
            <p key={`${al.message}-${i}`} className="text-[11px] text-[#AEAEB2]">
              {al.level} · {al.message}
            </p>
          ))}
        </section>
      ) : null}
      {agent.system_prompt ? (
        <section className="rd-sec">
          <div className="rd-tt">角色設定摘要</div>
          <p className="line-clamp-6 whitespace-pre-wrap text-[11px] leading-relaxed text-[#AEAEB2]">{agent.system_prompt}</p>
        </section>
      ) : null}
    </>
  );
}

interface AgentsMonitorPanelProps {
  focusAgentId?: string | null;
  onFocusAgent?: (id: string | null) => void;
  deskScope?: AgentDeskScope;
}

export default function AgentsMonitorPanel({ focusAgentId, onFocusAgent, deskScope = 'console' }: AgentsMonitorPanelProps) {
  const [data, setData] = useState<AgentMonitorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string>(focusAgentId || '');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [itemFilter, setItemFilter] = useState<WorkItemColumnKey>('executing');
  const [deskTab, setDeskTab] = useState<RoleDeskTab>('tasks');
  const [creating, setCreating] = useState(false);
  const [cloneFrom, setCloneFrom] = useState<RoleAgent | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [didAutoOpen, setDidAutoOpen] = useState(false);
  const [appliedDefaultTab, setAppliedDefaultTab] = useState(false);
  const [grillTrees, setGrillTrees] = useState<GrillTree[]>([]);
  const [l0, setL0] = useState<L0Snapshot | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchAgentMonitor();
      setData(next);
      setError(null);
      setSelectedId((current) =>
        pickDefaultAgentId(filterAgentsByDesk(next.agents, deskScope), focusAgentId || current),
      );
    } catch (err) {
      setError((err as Error).message);
    }
    try {
      const snap = await fetchRahoTree();
      setGrillTrees(snap.trees ?? []);
      setL0(snap.l0 ?? null);
    } catch {
      setGrillTrees([]);
      setL0(null);
    }
  }, [focusAgentId, deskScope]);

  const pollMs = data?.monitor_prefs?.poll_interval_ms ?? 5000;

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), Math.max(2000, pollMs));
    return () => clearInterval(timer);
  }, [refresh, pollMs]);

  useEffect(() => {
    if (!focusAgentId) return;
    const studio = isLinkinStudioAgent(focusAgentId);
    if (deskScope === 'linkin' ? studio : !studio) setSelectedId(focusAgentId);
  }, [focusAgentId, deskScope]);

  useEffect(() => {
    const pending = consumePendingDeskTab();
    if (pending) {
      setDeskTab(toDeskTab(pending));
      setAppliedDefaultTab(true);
    }
  }, []);

  useEffect(() => {
    const onJump = (event: Event) => {
      const { id, level, rahoLayer, deskTab: nextTab } = (event as CustomEvent<JumpAgentDetail>).detail ?? {};
      if (id) {
        const studio = isLinkinStudioAgent(id);
        if (id !== 'atomic_executor' && (deskScope === 'linkin' ? !studio : studio)) return;
        const roster = filterAgentsByDesk(
          data?.agents?.length ? data.agents : AGENT_FALLBACK_ROSTER,
          deskScope,
        );
        setSelectedId(pickDefaultAgentId(roster, id) || id);
        setDeskTab(toDeskTab(nextTab));
        setAppliedDefaultTab(true);
        return;
      }
      if (typeof rahoLayer === 'number') {
        setSelectedId((current) => {
          const roster = filterAgentsByDesk(
            data?.agents?.length ? data.agents : AGENT_FALLBACK_ROSTER,
            deskScope,
          );
          return pickDefaultAgentId(roster, rahoLayer === 2 ? 'atomic_executor' : current) || current;
        });
        setDeskTab(toDeskTab(nextTab));
        setAppliedDefaultTab(true);
        return;
      }
      if (typeof level === 'number') {
        setSelectedId((current) => {
          const roster = filterAgentsByDesk(
            data?.agents?.length ? data.agents : AGENT_FALLBACK_ROSTER,
            deskScope,
          );
          return roster.find((a) => a.level === level)?.id ?? current;
        });
        setDeskTab(toDeskTab(nextTab));
        setAppliedDefaultTab(true);
        return;
      }
      if (nextTab) {
        setDeskTab(toDeskTab(nextTab));
        setAppliedDefaultTab(true);
      }
    };
    window.addEventListener(JUMP_AGENT_EVENT, onJump);
    return () => window.removeEventListener(JUMP_AGENT_EVENT, onJump);
  }, [data?.agents, deskScope]);

  useEffect(() => {
    if (didAutoOpen || !data?.monitor_prefs?.auto_open_busy || focusAgentId) return;
    const busy = filterAgentsByDesk(data.agents, deskScope).find((a) => a.status === 'busy');
    if (busy) {
      setSelectedId(busy.id);
      setDidAutoOpen(true);
    }
  }, [data?.monitor_prefs?.auto_open_busy, data?.agents, focusAgentId, didAutoOpen, deskScope]);

  useEffect(() => {
    if (appliedDefaultTab) return;
    const tab = data?.monitor_prefs?.default_desk_tab;
    if (tab === 'tasks' || tab === 'monitor' || tab === 'settings' || tab === 'org' || tab === 'overview') {
      setDeskTab(toDeskTab(tab));
      setAppliedDefaultTab(true);
    }
  }, [appliedDefaultTab, data?.monitor_prefs?.default_desk_tab]);

  const roster = data?.agents?.length ? data.agents : AGENT_FALLBACK_ROSTER;
  const agents = filterAgentsByDesk(roster, deskScope);
  const selected = agents.find((a) => a.id === selectedId) ?? agents[0] ?? null;
  const quantDesk = isQuantDeskRole(selected?.id);
  const selectedGrill = useMemo(
    () => (selected ? nodesForRole(grillTrees, selected.id) : []),
    [grillTrees, selected],
  );

  useEffect(() => {
    if (deskTab === 'quant' && !quantDesk) setDeskTab('tasks');
  }, [deskTab, quantDesk]);

  const openDesk = (id: string, tab?: RoleDeskTab | 'org') => {
    setSelectedId(id);
    onFocusAgent?.(id);
    setExpandedId(null);
    if (tab) setDeskTab(toDeskTab(tab));
  };

  const revealGrill = () => {
    setDeskTab('tasks');
    window.requestAnimationFrame(() => {
      document.getElementById('role-grill-spine')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  useEffect(() => {
    if (!selected) return;
    if (!consumePendingGrillReveal()) return;
    revealGrill();
  }, [selected?.id]);

  const selectedRoute = selected
    ? (data?.catalog_meta?.api_routes ?? []).find((r) => r.id === selected.preferred_provider)
    : undefined;
  const selectedModelLabel = selected
    ? [
        routeDisplayName(selectedRoute),
        selected.preferred_model || (TIER_LABEL[selected.default_tier] ?? selected.default_tier),
      ]
        .filter(Boolean)
        .join(' · ')
    : '';
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas text-[#f7f8f8]">
      {error && (
        <div className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-[11px] text-amber-100">
          {error} · 已顯示角色目錄，後端恢復後會自動帶入任務
        </div>
      )}

      {!selected && (
        <div className="flex flex-1 items-center justify-center px-6 text-center">
          <p className="text-[13px] text-[#AEAEB2]">
            {deskScope === 'linkin' ? '尚無靈境工作室角色' : '尚無名冊'}
          </p>
        </div>
      )}

      {selected && (
        <div className="rd-shell">
          <RoleDeskHeader
            agent={selected}
            modelLabel={selectedModelLabel}
            deskTab={deskTab}
            onDeskTab={setDeskTab}
            showQuant={quantDesk}
          />
          {(selected.alerts?.length ?? 0) > 0 && (
            <div className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-[11px] text-amber-100">
              {selected.alerts![0].level} · {selected.alerts![0].message}
              {(selected.alerts!.length ?? 0) > 1 ? ` · 另 ${selected.alerts!.length - 1} 則` : ''}
            </div>
          )}
          <RoleStatsStrip agent={selected} />

          <div className={`rd-body ${deskTab === 'settings' ? 'rd-body--settings' : ''}`}>
            <div className="rd-tasks">
              {deskTab === 'settings' ? (
                  <div className="rd-pane">
                    <RoleSettingsPanel
                      agent={selected}
                      catalog={data?.catalog_meta}
                      agents={agents}
                      saving={saving}
                      error={saveError}
                      onCreate={
                        deskScope === 'console'
                          ? () => {
                              setCloneFrom(null);
                              setCreating(true);
                            }
                          : undefined
                      }
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
              ) : deskTab === 'quant' ? (
                <>
                  <div className="rd-th">
                    <h2>回測策略庫</h2>
                    <a href="#/monitor/lab/quant" className="rd-btn text-[11px] text-[#0A84FF]">
                      實驗室全屏
                    </a>
                    <a href="#/monitor/lab/maps" className="rd-btn text-[11px] text-[#0A84FF]">
                      策略圖
                    </a>
                  </div>
                  <div className="rd-pane">
                    <StrategyCatalogPanel embedded />
                  </div>
                </>
              ) : deskTab === 'monitor' ? (
                <>
                  <div className="rd-th"><h2>角色監控</h2></div>
                  <div className="rd-stack">
                    <RoleDeepMonitor agent={selected} />
                    <section className="rd-sec">
                      <div className="rd-tt">角色專屬</div>
                      <RoleMonitorExtras
                        agent={selected}
                        onOpenQuant={() => setDeskTab('quant')}
                        onOpenGrill={revealGrill}
                      />
                    </section>
                    <section className="rd-sec">
                      <div className="rd-tt">監控偏好</div>
                      <div className="rd-prefs">
                        <button
                          type="button"
                          className="rd-btn"
                          onClick={() => void updateAgentMonitorPrefs({ poll_interval_ms: pollMs === 5000 ? 8000 : 5000 }).then(() => refresh())}
                        >
                          輪詢 {pollMs / 1000}s
                        </button>
                        <button
                          type="button"
                          className={`rd-btn ${data?.monitor_prefs?.show_idle === false ? '' : 'on'}`}
                          onClick={() => void updateAgentMonitorPrefs({ show_idle: !(data?.monitor_prefs?.show_idle ?? true) }).then(() => refresh())}
                        >
                          待命
                        </button>
                        <button
                          type="button"
                          className={`rd-btn ${data?.monitor_prefs?.highlight_alerts === false ? '' : 'on'}`}
                          onClick={() =>
                            void updateAgentMonitorPrefs({ highlight_alerts: !(data?.monitor_prefs?.highlight_alerts ?? true) }).then(() => refresh())
                          }
                        >
                          突顯告警
                        </button>
                        <button
                          type="button"
                          className={`rd-btn ${data?.monitor_prefs?.auto_open_busy ? 'on' : ''}`}
                          onClick={() =>
                            void updateAgentMonitorPrefs({ auto_open_busy: !(data?.monitor_prefs?.auto_open_busy ?? false) }).then(() => refresh())
                          }
                        >
                          忙碌自動切入
                        </button>
                        <select
                          value={data?.monitor_prefs?.sort_by || 'level'}
                          onChange={(e) => void updateAgentMonitorPrefs({ sort_by: e.target.value }).then(() => refresh())}
                          className="rd-btn"
                        >
                          <option value="level">排序：層級</option>
                          <option value="name">排序：名稱</option>
                          <option value="status">排序：狀態</option>
                          <option value="cost">排序：花費</option>
                          <option value="queue">排序：佇列</option>
                        </select>
                        <select
                          value={data?.monitor_prefs?.group_by === 'category' ? 'category' : 'level'}
                          onChange={(e) => void updateAgentMonitorPrefs({ group_by: e.target.value }).then(() => refresh())}
                          className="rd-btn"
                        >
                          <option value="level">分組：層級</option>
                          <option value="category">分組：分類</option>
                        </select>
                      </div>
                    </section>
                  </div>
                </>
              ) : (
                <>
                  <div className="rd-th">
                    <h2>質詢鏈與任用 — {selected.work_items.length}</h2>
                  </div>
                  <div id="role-grill-spine" className="rd-grill-fuse">
                    <GrillTreePanel
                      embedded
                      compact
                      focusRoleId={selected.id}
                      onSelectRole={(id) => openDesk(id, 'tasks')}
                    />
                  </div>
                  <StatusColumnBoard
                    selectedKey={itemFilter}
                    onSelect={(key) => setItemFilter(key as WorkItemColumnKey)}
                    columns={WORK_ITEM_COLUMNS.map((col) => {
                      const items = itemsInColumn(selected.work_items, col.key);
                      return {
                        key: col.key,
                        label: col.label,
                        count: items.length,
                        children: items.map((item) => (
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
                        )),
                      };
                    })}
                  />
                </>
              )}
            </div>

            {deskTab !== 'settings' ? (
              <RoleRightPanel
                agent={selected}
                agents={agents}
                filter={itemFilter}
                onFilter={(key) => {
                  setItemFilter(key);
                  setDeskTab('tasks');
                }}
                onOpen={(id) => openDesk(id)}
                onOpenItem={(item) => {
                  setDeskTab('tasks');
                  setItemFilter(workItemColumnKey(item.status));
                  setExpandedId(`${item.task_id}-${item.id}-${item.kind}`);
                }}
                grillNodes={selectedGrill}
                l0={l0}
                onOpenGrill={revealGrill}
              />
            ) : null}
          </div>
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
