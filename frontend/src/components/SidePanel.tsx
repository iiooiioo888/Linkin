/**
 * SidePanel — 左側上下文面板。
 * Chat → 會話；Monitor → 完整導航（標題＋說明＋金邊）+ 虛擬滾動名冊。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { agentOpenCount, dispatchEditApiRoute, dispatchJumpAgent, dispatchNewApiRoute, filterAgentsByDesk, isAlertAgent, isLiveAgent, requestRoleGrillDesk, taskColumnKey, tasksInColumn, TASK_COLUMNS, API_ROUTES_CHANGED_EVENT, EDIT_API_ROUTE_EVENT, NEW_API_ROUTE_EVENT, type AgentDeskScope, type TaskColumnKey } from '../lib/agentUi';
import { agentRahoLabel, jumpToL0Kernel, COMMAND_CHAIN, INSPECT_CHAIN, KERNEL_CHAIN, RAHO_LAYERS, isRahoSpineRole } from '../lib/rahoUi';
import { AGENT_FALLBACK_ROSTER } from '../lib/monitorFallbacks';
import { fetchLlmOps } from '../api/client';
import type { ApiRoutePublic, ChatSession, RoleAgent, TaskSummary } from '../types';
import {
  LAB_NAV_GROUPS,
  type LabSubTab,
} from '../lib/labTabs';
import {
  activityTitle,
  navGroupsForActivity,
  resolveActivity,
  type ConsoleNavItem,
  type ConsoleNavKey,
} from '../lib/monitorTabs';
import { useMonitorStore } from '../stores/monitorStore';
import type { MonitorTab, ViewKey } from './AppShell';
import TraceRoster from './TraceRoster';

interface SidePanelProps {
  activeView: ViewKey;
  sessions: ChatSession[];
  activeSessionId: string;
  open: boolean;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
  onClose: () => void;
  monitorTab: MonitorTab;
  onMonitorTabChange: (tab: MonitorTab) => void;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;
  traceTaskId: string | null;
  onTraceTaskChange: (id: string | null) => void;
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
}

function formatRelative(ts: number): string {
  const diff = Date.now() - ts;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '剛剛';
  if (minutes < 60) return `${minutes} 分鐘前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小時前`;
  return new Date(ts).toLocaleDateString('zh-TW');
}

function SessionList({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}: {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
}) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  useEffect(() => {
    if (!confirmingId) return;
    const timer = setTimeout(() => setConfirmingId(null), 3000);
    return () => clearTimeout(timer);
  }, [confirmingId]);

  return (
    <>
      <div className="border-b border-white/[0.06] p-2.5">
        <p className="mb-2 px-0.5 text-[10px] font-bold uppercase tracking-wider text-[#636366]">對話</p>
        <button
          onClick={onNewSession}
          className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-[12px] font-medium text-[#F5F5F7] transition-colors hover:bg-white/[0.06]"
        >
          新對話
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5">
        {sessions.length === 0 && (
          <p className="mt-8 px-3 text-center text-[11px] text-[#636366]">尚無對話紀錄</p>
        )}
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group mb-0.5 flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 transition-colors ${
              session.id === activeSessionId
                ? 'bg-white/[0.06] text-[#F5F5F7]'
                : 'text-[#AEAEB2] hover:bg-white/[0.03] hover:text-[#F5F5F7]'
            }`}
            onClick={() => onSelectSession(session.id)}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-[#F5F5F7]">
                {session.title || '新對話'}
              </p>
              <p className="text-[10px] text-[#8E8E93]">{formatRelative(session.updatedAt)}</p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (confirmingId === session.id) {
                  onDeleteSession(session.id);
                  setConfirmingId(null);
                } else {
                  setConfirmingId(session.id);
                }
              }}
              className={`shrink-0 rounded-lg px-1.5 py-1 text-[10px] transition-all ${
                confirmingId === session.id
                  ? 'bg-[#FF3B30]/20 text-[#FF3B30] opacity-100'
                  : 'text-[#636366] opacity-0 hover:bg-[#FF3B30]/15 hover:text-[#FF3B30] group-hover:opacity-100'
              }`}
              aria-label="刪除會話"
            >
              {confirmingId === session.id ? '確認?' : '刪'}
            </button>
          </div>
        ))}
      </div>
      <div className="border-t border-white/[0.06] px-3 py-2 text-[10px] text-[#48484A]">
        本機儲存
      </div>
    </>
  );
}

type RosterRow =
  | { kind: 'header'; key: string; label: string; count: number }
  | { kind: 'agent'; key: string; agent: RoleAgent }
  | { kind: 'kernel'; key: string; label: string; short: string; layer: number };

const ORG_LEVELS = [
  { level: 0, label: '決策層' },
  { level: 1, label: '技術領導' },
  { level: 2, label: '領域領導' },
  { level: 3, label: '執行層' },
  { level: 4, label: '支援' },
] as const;

function AgentRoster({
  focusAgentId,
  onPick,
  deskScope = 'console',
}: {
  focusAgentId: string | null;
  onPick: (id: string) => void;
  deskScope?: AgentDeskScope;
}) {
  const storeAgents = useMonitorStore((s) => s.agents?.agents);
  const agents = filterAgentsByDesk(storeAgents?.length ? storeAgents : AGENT_FALLBACK_ROSTER, deskScope);
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<'all' | 'live' | 'alert'>('all');
  const listRef = useRef<VirtuosoHandle>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rank: Record<string, number> = { busy: 0, error: 1, waiting: 2, idle: 3, disabled: 4 };
    return agents
      .filter((a) => {
        if (scope === 'live' && !isLiveAgent(a)) return false;
        if (scope === 'alert' && !isAlertAgent(a)) return false;
        if (!q) return true;
        const hay = `${a.name} ${a.id} ${a.raho_label ?? ''} ${a.level_label ?? ''} ${a.description ?? ''} ${a.preferred_model ?? ''} ${(a.responsibilities ?? []).join(' ')}`.toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9));
  }, [agents, query, scope]);

  const rows: RosterRow[] = useMemo(() => {
    const out: RosterRow[] = [];
    if (deskScope === 'console') {
      const pushLane = (key: string, label: string, layers: readonly number[]) => {
        const laneRows: RosterRow[] = [];
        for (const layer of layers) {
          const meta = RAHO_LAYERS[layer];
          if (!meta) continue;
          if (layer === 5) {
            laneRows.push({
              kind: 'kernel',
              key: 'user',
              label: meta.full,
              short: meta.short,
              layer,
            });
            continue;
          }
          const hit =
            filtered.find((a) => a.id === meta.role_id) ||
            filtered.find((a) => a.raho_spine && a.raho_layer === layer);
          if (hit) {
            laneRows.push({ kind: 'agent', key: `spine-${hit.id}`, agent: hit });
          } else {
            laneRows.push({
              kind: 'kernel',
              key: meta.role_id || `layer-${layer}`,
              label: meta.full,
              short: meta.short,
              layer,
            });
          }
        }
        if (laneRows.length) {
          out.push({ kind: 'header', key, label, count: laneRows.length });
          out.push(...laneRows);
        }
      };
      pushLane('h-command', '指揮鏈 L5–L2', COMMAND_CHAIN);
      pushLane('h-inspect', '獨立審查 L1', INSPECT_CHAIN);
      pushLane('h-kernel', '環境核心 L0', KERNEL_CHAIN);
    }
    for (const lv of ORG_LEVELS) {
      const list = filtered.filter((a) => a.level === lv.level && !isRahoSpineRole(a.id));
      if (!list.length) continue;
      out.push({ kind: 'header', key: `h-${lv.level}`, label: lv.label, count: list.length });
      for (const agent of list) {
        out.push({ kind: 'agent', key: agent.id, agent });
      }
    }
    return out;
  }, [filtered, deskScope]);

  const searching = query.trim().length > 0;

  const clearFilters = () => {
    setScope('all');
    setQuery('');
  };

  const pickScope = (key: 'all' | 'live' | 'alert') => {
    setScope(key);
  };

  const filterTabs = [
    { key: 'all' as const, label: '全部', title: '顯示全部角色' },
    { key: 'live' as const, label: '限定', title: '只看執行中或等待中' },
    { key: 'alert' as const, label: '告警', title: '只看告警、錯誤或超預算' },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="ar-h">
        <span className="ar-ht">{deskScope === 'linkin' ? '工作室' : '指揮／審查／組織'}</span>
        <span className="ar-hc">{agents.length}</span>
      </div>
      <div className="ar-flt" role="tablist" aria-label="角色篩選">
        {filterTabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={scope === tab.key}
            title={tab.title}
            onClick={() => pickScope(tab.key)}
            className={`ar-fbtn ${scope === tab.key ? 'on' : ''} ${scope === tab.key && tab.key === 'alert' ? 'alert' : ''}`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="ar-search">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜尋角色..."
        />
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <p className="text-[12px] text-[#AEAEB2]">
            {searching ? '沒有符合搜尋的角色' : scope === 'alert' ? '目前沒有告警' : scope === 'live' ? '目前沒有限定角色' : '尚無名冊'}
          </p>
          {(scope !== 'all' || searching) && (
            <button
              type="button"
              onClick={clearFilters}
              className="mt-2 text-[11px] text-[#64D2FF] hover:underline"
            >
              顯示全部角色
            </button>
          )}
        </div>
      ) : (
      <Virtuoso
        ref={listRef}
        className="min-h-0 flex-1"
        data={rows}
        itemContent={(_i, row) => {
          if (row.kind === 'header') {
            return (
              <div className="ar-rg">
                <span>{row.label}</span>
                <span className="ar-rc">{row.count}</span>
              </div>
            );
          }
          if (row.kind === 'kernel') {
            const staticRow = row.layer === 5;
            return (
              <button
                type="button"
                disabled={staticRow}
                onClick={() => {
                  if (row.layer === 0) jumpToL0Kernel();
                  else if (!staticRow) onPick(row.key);
                }}
                className="ar-ri"
              >
                <span className={`ar-dot ${row.layer === 0 ? 'wait' : ''}`} />
                <span className="min-w-0 flex-1 truncate">
                  {row.short}
                  <span className="ml-1 text-[9px] text-[#636366]">{row.label}</span>
                </span>
              </button>
            );
          }
          const agent = row.agent;
          const active = agent.id === focusAgentId;
          const count = agentOpenCount(agent);
          const live = agent.status === 'busy';
          const wait = agent.status === 'waiting';
          const err = agent.status === 'error';
          return (
            <button
              type="button"
              onClick={() => {
                dispatchJumpAgent({ id: agent.id, level: agent.level, rahoLayer: agent.raho_layer });
                onPick(agent.id);
              }}
              className={`ar-ri ${active ? 'on' : ''}`}
            >
              <span className={`ar-dot ${live ? 'on' : wait ? 'wait' : err ? 'err' : ''}`} />
              <span className="min-w-0 flex-1 truncate">
                {agent.name}
                <span className="ml-1 text-[9px] text-[#636366]">{agentRahoLabel(agent)}</span>
                {agent.enabled === false ? <span className="ml-1 text-[9px] text-[#FF3B30]">停</span> : null}
              </span>
              {count > 0 ? <span className="ar-rr">{count}</span> : null}
            </button>
          );
        }}
      />
      )}
    </div>
  );
}

function ApiRouteRoster() {
  const [routes, setRoutes] = useState<ApiRoutePublic[]>([]);
  const [strategy, setStrategy] = useState('role_preferred');
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      fetchLlmOps()
        .then((ops) => {
          setRoutes(ops.api_routes ?? []);
          setStrategy(ops.route_strategy || 'role_preferred');
        })
        .catch(() => {
          setRoutes([]);
        });
    void load();
    const timer = setInterval(() => void load(), 8000);
    window.addEventListener(API_ROUTES_CHANGED_EVENT, load);
    const onEdit = (e: Event) => setActiveId((e as CustomEvent<string>).detail || null);
    const onNew = () => setActiveId(null);
    window.addEventListener(EDIT_API_ROUTE_EVENT, onEdit);
    window.addEventListener(NEW_API_ROUTE_EVENT, onNew);
    return () => {
      clearInterval(timer);
      window.removeEventListener(API_ROUTES_CHANGED_EVENT, load);
      window.removeEventListener(EDIT_API_ROUTE_EVENT, onEdit);
      window.removeEventListener(NEW_API_ROUTE_EVENT, onNew);
    };
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 space-y-1.5 border-b border-white/[0.06] px-3 pb-3 pt-2">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#636366]">已配置的 API</p>
          <button
            type="button"
            onClick={() => dispatchNewApiRoute()}
            className="rounded-md px-1.5 py-0.5 text-[10px] text-[#64D2FF] hover:bg-white/[0.06]"
          >
            新增
          </button>
        </div>
        <p className="text-[10px] text-[#8E8E93]">
          {routes.length} 組 · 策略 {strategy}
        </p>
      </div>
      {routes.length === 0 ? (
        <p className="px-3 py-8 text-center text-[11px] text-[#636366]">
          尚未加入 API。請在右側選擇供應商並填入金鑰。
        </p>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-1.5">
          {routes.map((route) => (
            <button
              key={route.id}
              type="button"
              onClick={() => dispatchEditApiRoute(route.id)}
              className={`mx-1.5 mb-0.5 flex w-[calc(100%-12px)] items-center gap-2 rounded-lg px-2.5 py-1.5 text-left ${
                activeId === route.id
                  ? 'bg-white/[0.06] text-[#F5F5F7]'
                  : 'text-[#AEAEB2] hover:bg-white/[0.03] hover:text-[#F5F5F7]'
              }`}
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  !route.enabled ? 'bg-[#8E8E93]' : route.configured ? 'bg-[#30D158]' : 'bg-[#FF9F0A]'
                }`}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-medium text-[#F5F5F7]">
                  {route.name}
                  {route.is_default ? <span className="ml-1 text-[9px] text-[#64D2FF]">預設</span> : null}
                </span>
                <span className="block truncate text-[10px] text-[#636366]">
                  {route.provider_label || route.provider} · {route.allowed_models.length} 模型
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const TASK_STATUS_DOT: Record<string, string> = {
  pending: 'bg-[#FF9500]',
  running: 'bg-[#007AFF] animate-pulse',
  completed: 'bg-[#34C759]',
  failed: 'bg-[#FF3B30]',
  cancelled: 'bg-[#8E8E93]',
  interrupted: 'bg-[#FF9500]',
};

const EMPTY_TASKS: TaskSummary[] = [];

const selectTaskRoster = (s: ReturnType<typeof useMonitorStore.getState>) =>
  s.dashboard?.tasks ?? EMPTY_TASKS;

type TaskRosterRow =
  | { kind: 'header'; key: TaskColumnKey; label: string; count: number }
  | { kind: 'task'; key: string; task: TaskSummary };

function TaskRoster({
  focusTaskId,
  onPick,
}: {
  focusTaskId: string | null;
  onPick: (id: string) => void;
}) {
  const tasks = useMonitorStore(useShallow(selectTaskRoster));
  const [query, setQuery] = useState('');
  const [openCols, setOpenCols] = useState<Set<TaskColumnKey>>(() => new Set(['queue', 'running', 'done']));

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? tasks.filter((t) => t.query.toLowerCase().includes(q) || t.task_id.includes(q))
      : tasks;
    return list.slice(0, 80);
  }, [tasks, query]);

  const rows: TaskRosterRow[] = useMemo(() => {
    const out: TaskRosterRow[] = [];
    for (const col of TASK_COLUMNS) {
      const list = tasksInColumn(filtered, col.key);
      out.push({ kind: 'header', key: col.key, label: col.label, count: list.length });
      if (!openCols.has(col.key)) continue;
      for (const task of list) {
        out.push({ kind: 'task', key: task.task_id, task });
      }
    }
    return out;
  }, [filtered, openCols]);

  useEffect(() => {
    if (!focusTaskId) return;
    const task = tasks.find((t) => t.task_id === focusTaskId);
    if (!task) return;
    const col = taskColumnKey(task.status);
    setOpenCols((cur) => (cur.has(col) ? cur : new Set(cur).add(col)));
  }, [focusTaskId, tasks]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="ar-h">
        <span className="ar-ht">任務列表</span>
        <span className="ar-hc">{tasks.length}</span>
      </div>
      <div className="ar-search">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜尋任務／ID"
          className="w-full rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[11px] text-[#F5F5F7] placeholder:text-[#636366] outline-none focus:border-[#007AFF]/50"
        />
      </div>
      {filtered.length === 0 ? (
        <p className="px-3 py-8 text-center text-[11px] text-[#636366]">
          {tasks.length === 0 ? '尚無任務紀錄' : '無符合結果'}
        </p>
      ) : (
        <Virtuoso
          className="min-h-0 flex-1"
          data={rows}
          computeItemKey={(_i, row) => row.key}
          itemContent={(_i, row) => {
            if (row.kind === 'header') {
              const open = openCols.has(row.key);
              return (
                <button
                  type="button"
                  onClick={() => {
                    setOpenCols((cur) => {
                      const next = new Set(cur);
                      if (next.has(row.key)) next.delete(row.key);
                      else next.add(row.key);
                      return next;
                    });
                  }}
                  className="ar-rg"
                >
                  <span className="inline-block w-2 font-mono text-[#48484A]">{open ? '▾' : '▸'}</span>
                  <span>{row.label}</span>
                  <span className="ml-auto font-mono text-[10px] text-[#636366]">{row.count}</span>
                </button>
              );
            }
            const { task } = row;
            const active = task.task_id === focusTaskId;
            const dot = TASK_STATUS_DOT[task.status] ?? 'bg-[#8E8E93]';
            return (
              <button
                type="button"
                onClick={() => onPick(task.task_id)}
                className={`mx-2 mb-0.5 flex w-[calc(100%-16px)] items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors ${
                  active
                    ? 'bg-white/[0.06] text-[#F5F5F7]'
                    : 'text-[#AEAEB2] hover:bg-white/[0.03] hover:text-[#F5F5F7]'
                }`}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-medium text-[#F5F5F7]">
                    {task.query || task.task_id.slice(0, 8)}
                  </span>
                  <span className="block truncate text-[10px] text-[#636366]">
                    {task.resolved_path || task.strategy} · {task.phase}
                  </span>
                </span>
              </button>
            );
          }}
        />
      )}
    </div>
  );
}

function TabBtn({
  item,
  active,
  onClick,
}: {
  item: ConsoleNavItem | { key: string; icon: string; label: string; hint?: string };
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={item.hint}
      className={`sp-item ${active ? 'on' : ''}`}
    >
      <span className="sp-item-ic">{item.icon}</span>
      <span className="sp-item-txt">
        <span className="sp-item-l">{item.label}</span>
        {item.hint ? <span className="sp-item-h">{item.hint}</span> : null}
      </span>
    </button>
  );
}

function LabSidebar({
  labSubTab,
  onLabSubTabChange,
}: {
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav className="sp-nav pb-3" aria-label="實驗室">
        {LAB_NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <div className="sp-group">{group.label}</div>
            <div className="sp-list">
              {group.items.map((item) => (
                <TabBtn
                  key={item.key}
                  item={item}
                  active={labSubTab === item.key}
                  onClick={() => onLabSubTabChange(item.key)}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );
}

function MonitorSidebar({
  activeView,
  monitorTab,
  onClose,
  focusAgentId,
  onFocusAgent,
  focusTaskId,
  onFocusTask,
  onMonitorTabChange,
  labSubTab,
  onLabSubTabChange,
  traceTaskId,
  onTraceTaskChange,
}: {
  activeView: ViewKey;
  monitorTab: MonitorTab;
  onClose: () => void;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;
  onMonitorTabChange: (tab: MonitorTab) => void;
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
  traceTaskId: string | null;
  onTraceTaskChange: (id: string | null) => void;
}) {
  const activity = resolveActivity(activeView, monitorTab);
  const onLab = activity === 'lab';
  const navGroups = navGroupsForActivity(activity);
  const onAgentsTab = activeView === 'monitor' && monitorTab === 'agents';
  const onStudioTab = activeView === 'monitor' && monitorTab === 'studio';
  const onGrillTab = activeView === 'monitor' && monitorTab === 'grill';
  const onMemoryTab = activeView === 'monitor' && monitorTab === 'memory';
  const onRoleDesk = onAgentsTab || onStudioTab || onGrillTab || onMemoryTab;
  const onTasksTab = activeView === 'monitor' && monitorTab === 'tasks';
  const onLlmTab = activeView === 'monitor' && monitorTab === 'llm';
  const onTraces = activeView === 'traces';
  const currentKey: ConsoleNavKey = onTraces ? 'traces' : monitorTab;

  const pick = (key: ConsoleNavKey) => {
    if (key === 'traces') {
      onTraceTaskChange(traceTaskId);
      return;
    }
    onMonitorTabChange(key);
    if (key !== 'agents' && key !== 'studio' && key !== 'grill' && key !== 'memory' && focusAgentId) onFocusAgent(null);
    if (key !== 'tasks' && focusTaskId) onFocusTask(null);
    if (key !== 'agents' && key !== 'studio' && key !== 'grill' && key !== 'memory' && key !== 'tasks' && key !== 'llm') onClose();
  };

  if (onLab) {
    return <LabSidebar labSubTab={labSubTab} onLabSubTabChange={onLabSubTabChange} />;
  }

  const showRoster = onRoleDesk || onTasksTab || onTraces || onLlmTab;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav
        className={showRoster ? 'sp-nav sp-nav--roster' : 'sp-nav'}
        aria-label={activityTitle(activity)}
      >
        {navGroups.map((group) => (
          <div key={group.id}>
            <div className="sp-group">{group.label}</div>
            <div className="sp-list">
              {group.items.map((item) => (
                <TabBtn
                  key={item.key}
                  item={item}
                  active={currentKey === item.key}
                  onClick={() => pick(item.key)}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {onRoleDesk ? (
        <AgentRoster
          deskScope={onStudioTab ? 'linkin' : 'console'}
          focusAgentId={onMemoryTab ? 'environment_kernel' : focusAgentId}
          onPick={(id) => {
            if (id === 'environment_kernel') {
              jumpToL0Kernel();
              return;
            }
            onFocusAgent(id);
            onMonitorTabChange(onStudioTab ? 'studio' : 'agents');
            if (onGrillTab) requestRoleGrillDesk(id);
          }}
        />
      ) : onTasksTab ? (
        <TaskRoster
          focusTaskId={focusTaskId}
          onPick={(id) => {
            onFocusTask(id);
            onMonitorTabChange('tasks');
          }}
        />
      ) : onLlmTab ? (
        <ApiRouteRoster />
      ) : onTraces ? (
        <TraceRoster
          selectedTaskId={traceTaskId}
          onPick={(id) => {
            onTraceTaskChange(id);
            onClose();
          }}
        />
      ) : null}
    </div>
  );
}

export default function SidePanel({
  activeView,
  sessions,
  activeSessionId,
  open,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  onClose,
  monitorTab,
  onMonitorTabChange,
  focusAgentId,
  onFocusAgent,
  focusTaskId,
  onFocusTask,
  traceTaskId,
  onTraceTaskChange,
  labSubTab,
  onLabSubTabChange,
}: SidePanelProps) {
  return (
    <>
      {open && (
        <div className="fixed inset-0 z-20 bg-black/50 md:hidden" onClick={onClose} />
      )}

      <aside
        className={`fixed inset-y-10 left-11 z-30 flex w-60 flex-col overflow-hidden border-r border-white/[0.06] apple-chrome transition-transform md:static md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] p-2 md:hidden">
          <span className="text-[11px] font-bold text-[#AEAEB2]">導航</span>
          <button onClick={onClose} className="rounded-lg px-2 py-0.5 text-[#8E8E93] hover:bg-white/[0.06]">
            ✕
          </button>
        </div>

        {activeView === 'chat' && (
          <SessionList
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={onSelectSession}
            onNewSession={onNewSession}
            onDeleteSession={onDeleteSession}
          />
        )}
        {(activeView === 'monitor' || activeView === 'traces') && (
          <MonitorSidebar
            activeView={activeView}
            monitorTab={monitorTab}
            onMonitorTabChange={onMonitorTabChange}
            onClose={onClose}
            focusAgentId={focusAgentId}
            onFocusAgent={onFocusAgent}
            focusTaskId={focusTaskId}
            onFocusTask={onFocusTask}
            labSubTab={labSubTab}
            onLabSubTabChange={onLabSubTabChange}
            traceTaskId={traceTaskId}
            onTraceTaskChange={onTraceTaskChange}
          />
        )}
      </aside>
    </>
  );
}
