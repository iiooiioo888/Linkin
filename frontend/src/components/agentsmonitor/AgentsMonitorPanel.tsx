/**
 * AgentsMonitorPanel — 每位公司角色一張獨立工作台。
 * 每位角色一張工作台：任用與組織回報。
 * 角色名冊在左側 SidePanel；總覽是控制台「即時」，不在此頁重複。
 *
 * 第七輪重構：JSX 區塊已拆至 ./agentsmonitor/ 子元件；本檔保留全部 state／effects／操作邏輯，
 * 子元件以 props 驅動（hooks 呼叫順序與資料流不變）。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createCustomAgent,
  fetchAgentMonitor,
  fetchRahoTree,
} from '../../api/client';
import {
  JUMP_AGENT_EVENT,
  TIER_LABEL,
  consumePendingDeskTab,
  consumePendingGrillReveal,
  filterAgentsByDesk,
  isLinkinStudioAgent,
  isQuantDeskRole,
  pickDefaultAgentId,
  routeDisplayName,
  workItemColumnKey,
  type AgentDeskScope,
  type JumpAgentDetail,
  type WorkItemColumnKey,
} from '../../lib/agentUi';
import { AGENT_FALLBACK_ROSTER } from '../../lib/monitorFallbacks';
import { nodesForRole } from '../../lib/rahoUi';
import type { AgentMonitorData, GrillTree, L0Snapshot, RahoSnapshot, RoleAgent } from '../../types';
import AgentExecutionTree from '../AgentExecutionTree';
import { RoleDeskPanes } from './RoleDeskPanes';
import { CreateRoleModal } from '../RoleSettingsPanel';
import RoleV3Desk from '../RoleV3Desk';
import { RoleDeskHeader, RoleRightPanel, RoleStatsStrip, type RoleDeskTab } from '../RoleDeskLayout';
import { ConsoleEmpty, ConsoleRdShell, PanelShell } from '../ui/ConsoleLayout';
import { AccountBudgetBanner } from '../RoleBudgetSummary';

function toDeskTab(tab?: string | null): RoleDeskTab {
  if (tab === 'monitor' || tab === 'settings' || tab === 'quant' || tab === 'list') return tab;
  return 'tasks';
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
  const [, setExpandedId] = useState<string | null>(null);
  const [itemFilter, setItemFilter] = useState<WorkItemColumnKey>('executing');
  const [deskTab, setDeskTab] = useState<RoleDeskTab>('tasks');
  const [creating, setCreating] = useState(false);
  const [cloneFrom, setCloneFrom] = useState<RoleAgent | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [didAutoOpen, setDidAutoOpen] = useState(false);
  const [appliedDefaultTab, setAppliedDefaultTab] = useState(false);
  const [grillTrees, setGrillTrees] = useState<GrillTree[]>([]);
  const [rahoSnap, setRahoSnap] = useState<RahoSnapshot | null>(null);
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
      setRahoSnap(snap);
      setGrillTrees(snap.trees ?? []);
      setL0(snap.l0 ?? null);
    } catch {
      setRahoSnap(null);
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
    if (deskScope === 'studio' ? studio : !studio) setSelectedId(focusAgentId);
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
        if (id !== 'atomic_executor' && (deskScope === 'studio' ? !studio : studio)) return;
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
      if (consumePendingGrillReveal()) {
        window.requestAnimationFrame(() => {
          document.getElementById('role-system')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
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
    if (tab === 'tasks' || tab === 'list' || tab === 'monitor' || tab === 'settings' || tab === 'org' || tab === 'overview') {
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
      document.getElementById('role-system')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  useEffect(() => {
    if (!selected) return;
    if (!consumePendingGrillReveal()) return;
    revealGrill();
  }, [selected?.id, deskTab]);

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
    <PanelShell scroll={false}>
      {error && (
        <div className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-6 py-2 text-[11px] text-amber-100">
          {error} · 已顯示角色目錄，後端恢復後會自動帶入任務
        </div>
      )}

      <div className="agents-monitor-split">
        <AgentExecutionTree
          agents={agents}
          selectedId={selected?.id ?? null}
          generatedAt={data?.generated_at}
          onSelectRole={(id) => openDesk(id)}
          onSelectWork={(roleId) => openDesk(roleId, 'tasks')}
        />
        <div className="agents-monitor-desk">

      {!selected && (
        <ConsoleEmpty className="flex flex-1 items-center justify-center">
          <p className="text-[13px] text-[var(--console-sub)]">
            {deskScope === 'studio' ? '尚無工作室角色' : '尚無名冊'}
          </p>
        </ConsoleEmpty>
      )}

      {selected && (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <RoleDeskHeader
            agent={selected}
            agents={agents}
            modelLabel={selectedModelLabel}
            deskTab={deskTab}
            onDeskTab={setDeskTab}
            onSelectAgent={(id) => openDesk(id)}
            showQuant={quantDesk}
          />
          {(selected.alerts?.length ?? 0) > 0 && (
            <div className="shrink-0 border-b border-amber-500/30 bg-amber-500/10 px-6 py-2 text-[11px] text-amber-100">
              {selected.alerts![0].level} · {selected.alerts![0].message}
              {(selected.alerts!.length ?? 0) > 1 ? ` · 另 ${selected.alerts!.length - 1} 則` : ''}
            </div>
          )}
          {deskTab === 'tasks' && data?.account_budget ? (
            <div className="shrink-0 border-b border-[var(--console-line)] px-6 py-2">
              <AccountBudgetBanner summary={data.account_budget} />
            </div>
          ) : null}

          {deskTab === 'tasks' ? (
            <RoleV3Desk
              agent={selected}
              agents={agents}
              rahoSnap={rahoSnap}
              grillNodes={selectedGrill}
              l0={l0}
              onSelectAgent={(id) => openDesk(id)}
              onOpenGrill={revealGrill}
            />
          ) : (
            <ConsoleRdShell>
              <RoleStatsStrip agent={selected} />
              <div className={`rd-body ${deskTab === 'settings' ? 'rd-body--settings' : ''}`}>
                <RoleDeskPanes
                  deskTab={deskTab}
                  selected={selected}
                  agents={agents}
                  data={data}
                  deskScope={deskScope}
                  saving={saving}
                  saveError={saveError}
                  pollMs={pollMs}
                  setSelectedId={setSelectedId}
                  setDeskTab={setDeskTab}
                  setSaving={setSaving}
                  setSaveError={setSaveError}
                  setCreating={setCreating}
                  setCloneFrom={setCloneFrom}
                  refresh={refresh}
                />

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
                    l0={l0}
                  />
                ) : null}
              </div>
            </ConsoleRdShell>
          )}
        </div>
      )}
        </div>
      </div>
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
    </PanelShell>
  );
}
