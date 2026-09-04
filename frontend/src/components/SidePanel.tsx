/**
 * SidePanel — 左側上下文面板。
 * Chat → 會話；Monitor → 精簡分頁 + 虛擬滾動名冊。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useShallow } from 'zustand/react/shallow';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import { AGENT_STATUS_META, agentOpenCount, dispatchJumpAgent, isAlertAgent, isLiveAgent } from '../lib/agentUi';
import { AGENT_FALLBACK_ROSTER } from '../lib/monitorFallbacks';
import {
  LAB_NAV_GROUPS,
  type LabSubTab,
} from '../lib/labTabs';
import {
  MONITOR_NAV_GROUPS,
  activityTitle,
  navGroupForTab,
  resolveActivity,
  type ConsoleNavItem,
  type ConsoleNavKey,
} from '../lib/monitorTabs';
import { useMonitorStore } from '../stores/monitorStore';
import type { ChatSession, RoleAgent, TaskSummary } from '../types';
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
  | { kind: 'agent'; key: string; agent: RoleAgent };

const ROSTER_LEVELS = [
  { level: 0, short: 'L0', label: '決策層' },
  { level: 1, short: 'L1', label: '技術領導' },
  { level: 2, short: 'L2', label: '領域領導' },
  { level: 3, short: 'L3', label: '執行層' },
  { level: 4, short: 'L4', label: '支援' },
] as const;

function AgentRoster({
  focusAgentId,
  onPick,
}: {
  focusAgentId: string | null;
  onPick: (id: string) => void;
}) {
  const storeAgents = useMonitorStore((s) => s.agents?.agents);
  const agents = storeAgents?.length ? storeAgents : AGENT_FALLBACK_ROSTER;
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState<'all' | 'live' | 'alert'>('all');
  const listRef = useRef<VirtuosoHandle>(null);

  const liveCount = useMemo(() => agents.filter(isLiveAgent).length, [agents]);
  const alertCount = useMemo(() => agents.filter(isAlertAgent).length, [agents]);
  const enabledCount = useMemo(
    () => agents.filter((a) => a.enabled !== false).length,
    [agents],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rank: Record<string, number> = { busy: 0, error: 1, waiting: 2, idle: 3, disabled: 4 };
    return agents
      .filter((a) => {
        if (scope === 'live' && !isLiveAgent(a)) return false;
        if (scope === 'alert' && !isAlertAgent(a)) return false;
        if (!q) return true;
        const hay = `${a.name} ${a.id} ${a.description ?? ''} ${(a.responsibilities ?? []).join(' ')}`.toLowerCase();
        return hay.includes(q);
      })
      .sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9));
  }, [agents, query, scope]);

  const rows: RosterRow[] = useMemo(() => {
    const out: RosterRow[] = [];
    for (const lv of ROSTER_LEVELS) {
      const list = filtered.filter((a) => a.level === lv.level);
      if (!list.length) continue;
      out.push({ kind: 'header', key: `h-${lv.level}`, label: `${lv.short} ${lv.label}`, count: list.length });
      for (const agent of list) {
        out.push({ kind: 'agent', key: agent.id, agent });
      }
    }
    return out;
  }, [filtered]);

  const jumpToLevel = (level: number) => {
    const idx = rows.findIndex((r) => r.kind === 'header' && r.key === `h-${level}`);
    if (idx >= 0) {
      listRef.current?.scrollToIndex({ index: idx, align: 'start', behavior: 'smooth' });
    }
    dispatchJumpAgent({ level });
  };

  const searching = query.trim().length > 0;

  const clearFilters = () => {
    setScope('all');
    setQuery('');
  };

  const pickScope = (key: 'all' | 'live' | 'alert') => {
    setScope(key);
  };

  const filterTabs = [
    { key: 'all' as const, label: '全部', count: agents.length, title: '顯示全部角色' },
    { key: 'live' as const, label: '活躍', count: liveCount, title: '只看執行中或等待中' },
    { key: 'alert' as const, label: '告警', count: alertCount, title: '只看告警、錯誤或超預算' },
  ];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 space-y-2 border-b border-white/[0.06] px-3 pb-3 pt-2">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-[#636366]">左側跳轉</p>
          <p className="text-[10px] text-[#8E8E93]" title="啟用席次／名冊總數">
            {enabledCount}/{agents.length}
          </p>
        </div>
        <div className="flex flex-wrap gap-1" aria-label="依層級跳轉">
          {ROSTER_LEVELS.map((lv) => {
            const count = filtered.filter((a) => a.level === lv.level).length;
            return (
              <button
                key={lv.level}
                type="button"
                disabled={count === 0}
                title={count ? `跳到 ${lv.short} ${lv.label}` : `${lv.short} 目前沒有符合的角色`}
                onClick={() => jumpToLevel(lv.level)}
                className={`rounded-md px-1.5 py-0.5 text-[10px] leading-none ${
                  count === 0
                    ? 'cursor-not-allowed text-[#48484A]'
                    : 'bg-white/[0.05] text-[#AEAEB2] hover:bg-white/[0.1] hover:text-[#F5F5F7]'
                }`}
              >
                {lv.short}
                <span className="ml-0.5 font-mono text-[#636366]">{count}</span>
              </button>
            );
          })}
        </div>
        <div className="flex rounded-xl bg-white/[0.04] p-0.5" role="tablist" aria-label="角色篩選">
          {filterTabs.map((tab) => {
            const active = scope === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                title={tab.title}
                onClick={() => pickScope(tab.key)}
                className={`flex min-w-0 flex-1 items-center justify-center gap-1 rounded-lg px-1 py-1.5 text-[11px] leading-none transition-colors ${
                  active
                    ? tab.key === 'alert'
                      ? 'bg-[#FF453A]/15 font-medium text-[#FF453A] shadow-sm'
                      : tab.key === 'live'
                        ? 'bg-[#30D158]/15 font-medium text-[#30D158] shadow-sm'
                        : 'bg-white/[0.1] font-medium text-[#F5F5F7] shadow-sm'
                    : 'text-[#8E8E93] hover:text-[#AEAEB2]'
                }`}
              >
                {tab.label}
                <span className="apple-data text-[10px]">{tab.count}</span>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-1.5">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜尋名稱、職責…"
            className="min-w-0 flex-1 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[11px] text-[#F5F5F7] placeholder:text-[#636366] outline-none focus:border-[#007AFF]/50"
          />
          {(searching || scope !== 'all') && (
            <button
              type="button"
              onClick={clearFilters}
              className="shrink-0 rounded-lg px-1.5 py-1 text-[10px] text-[#64D2FF] hover:bg-white/[0.06]"
              title="清除篩選與搜尋"
            >
              清除
              <span className="ml-1 font-mono text-[#8E8E93]">{filtered.length}</span>
            </button>
          )}
        </div>
      </div>
      {rows.length === 0 ? (
        <div className="px-4 py-8 text-center">
          <p className="text-[12px] text-[#AEAEB2]">
            {searching ? '沒有符合搜尋的角色' : scope === 'alert' ? '目前沒有告警' : scope === 'live' ? '目前沒有活躍角色' : '尚無名冊'}
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
              <p className="px-3 pb-1 pt-3 text-[10px] font-bold uppercase tracking-wider text-[#636366]">
                {row.label}
                <span className="ml-1 font-mono text-[#48484A]">{row.count}</span>
              </p>
            );
          }
          const agent = row.agent;
          const meta = AGENT_STATUS_META[agent.status] ?? AGENT_STATUS_META.idle;
          const active = agent.id === focusAgentId;
          const count = agentOpenCount(agent);
          return (
            <button
              type="button"
              onClick={() => {
                dispatchJumpAgent({ id: agent.id, level: agent.level });
                onPick(agent.id);
              }}
              className={`mx-2 mb-0.5 flex w-[calc(100%-16px)] items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors ${
                active
                  ? 'bg-white/[0.06] text-[#F5F5F7]'
                  : 'text-[#AEAEB2] hover:bg-white/[0.03] hover:text-[#F5F5F7]'
              }`}
            >
              <span
                className={`apple-dot shrink-0 ${agent.status === 'busy' ? 'apple-dot--ok' : ''}`}
                style={
                  agent.status === 'busy'
                    ? undefined
                    : agent.status === 'error'
                      ? { background: '#FF3B30', boxShadow: '0 0 0 2px #FF3B3033, 0 0 10px #FF3B3055' }
                      : agent.status === 'waiting'
                        ? { background: '#FF9500', boxShadow: '0 0 0 2px #FF950033, 0 0 10px #FF950055' }
                        : { background: '#8E8E93', boxShadow: '0 0 0 2px #8E8E9333' }
                }
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-medium text-[#F5F5F7]">
                  {agent.name}
                  {agent.enabled === false ? <span className="ml-1 text-[9px] text-[#FF3B30]">停</span> : null}
                </span>
                <span className={`block truncate text-[10px] ${meta.text}`}>
                  {meta.label}
                  {count > 0 ? ` · ${count} 項` : ''}
                </span>
              </span>
              {count > 0 && <span className="apple-data text-[10px] text-[#8E8E93]">{count}</span>}
            </button>
          );
        }}
      />
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

function TaskRoster({
  focusTaskId,
  onPick,
}: {
  focusTaskId: string | null;
  onPick: (id: string) => void;
}) {
  const tasks = useMonitorStore(useShallow(selectTaskRoster));
  const running = tasks.filter((t) => t.status === 'running' || t.status === 'pending').length;
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? tasks.filter((t) => t.query.toLowerCase().includes(q) || t.task_id.includes(q))
      : tasks;
    return list.slice(0, 80);
  }, [tasks, query]);

  const renderItem = useCallback(
    (_i: number, task: TaskSummary) => {
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
    },
    [focusTaskId, onPick],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 space-y-2 border-b border-white/[0.06] px-3 pb-3 pt-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-[#636366]">
          {tasks.length} 筆 · {running} 執行中
        </p>
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
          data={filtered}
          computeItemKey={(_i, task) => task.task_id}
          itemContent={renderItem}
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
      className={`relative flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors ${
        active
          ? 'bg-white/[0.06] text-[#F5F5F7]'
          : 'text-[#98989D] hover:bg-white/[0.03] hover:text-[#F5F5F7]'
      }`}
    >
      <span className="w-4 shrink-0 text-center text-[12px] leading-none opacity-70">{item.icon}</span>
      <span className="min-w-0 flex-1">
        <span className={`block truncate text-[12px] ${active ? 'font-medium' : ''}`}>{item.label}</span>
        {item.hint && (
          <span className="block truncate text-[10px] text-[#636366]">{item.hint}</span>
        )}
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
  const activeGroup = LAB_NAV_GROUPS.find((g) => g.items.some((i) => i.key === labSubTab))?.id ?? 'integrate';
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => ({
    integrate: true,
    experiment: activeGroup === 'experiment',
  }));

  useEffect(() => {
    setOpenGroups((prev) => (prev[activeGroup] ? prev : { ...prev, [activeGroup]: true }));
  }, [activeGroup]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav className="min-h-0 flex-1 overflow-y-auto pb-3" aria-label="實驗室">
        {LAB_NAV_GROUPS.map((group) => {
          const open = openGroups[group.id] ?? group.id === 'integrate';
          return (
            <div key={group.id}>
              <GroupToggle
                label={group.label}
                open={open}
                onToggle={() => setOpenGroups((prev) => ({ ...prev, [group.id]: !open }))}
              />
              {open && (
                <div className="space-y-0.5 px-2 pb-1">
                  {group.items.map((item) => (
                    <TabBtn
                      key={item.key}
                      item={item}
                      active={labSubTab === item.key}
                      onClick={() => onLabSubTabChange(item.key)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </div>
  );
}

function GroupToggle({
  label,
  open,
  onToggle,
}: {
  label: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="flex w-full items-center gap-1.5 px-3 pb-1 pt-2.5 text-[10px] font-bold uppercase tracking-wider text-[#636366] hover:text-[#AEAEB2]"
    >
      <span className="inline-block w-2 font-mono text-[#48484A]">{open ? '▾' : '▸'}</span>
      <span>{label}</span>
    </button>
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
  const onAgentsTab = activeView === 'monitor' && monitorTab === 'agents';
  const onTasksTab = activeView === 'monitor' && monitorTab === 'tasks';
  const onTraces = activeView === 'traces';
  const currentKey: ConsoleNavKey = onTraces ? 'traces' : monitorTab;
  const activeGroup = navGroupForTab(currentKey);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => ({
    execute: true,
    observe: activeGroup === 'observe',
    system: activeGroup === 'system',
    linkin: true,
  }));

  useEffect(() => {
    if (!activeGroup) return;
    setOpenGroups((prev) => (prev[activeGroup] ? prev : { ...prev, [activeGroup]: true }));
  }, [activeGroup]);

  const pick = (key: ConsoleNavKey) => {
    if (key === 'traces') {
      onTraceTaskChange(traceTaskId);
      return;
    }
    onMonitorTabChange(key);
    if (key !== 'agents' && focusAgentId) onFocusAgent(null);
    if (key !== 'tasks' && focusTaskId) onFocusTask(null);
    if (key !== 'agents' && key !== 'tasks') onClose();
  };

  if (onLab) {
    return <LabSidebar labSubTab={labSubTab} onLabSubTabChange={onLabSubTabChange} />;
  }

  const showRoster = onAgentsTab || onTasksTab || onTraces;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav
        className={`shrink-0 overflow-y-auto ${showRoster ? 'max-h-[42%] border-b border-white/[0.06]' : 'min-h-0 flex-1'}`}
        aria-label={activityTitle(activity)}
      >
        {MONITOR_NAV_GROUPS.map((group) => {
          const open = openGroups[group.id] ?? group.id === 'execute';
          return (
            <div key={group.id}>
              <GroupToggle
                label={group.label}
                open={open}
                onToggle={() => setOpenGroups((prev) => ({ ...prev, [group.id]: !open }))}
              />
              {open && (
                <div className="space-y-0.5 px-2 pb-1">
                  {group.items.map((item) => (
                    <TabBtn
                      key={item.key}
                      item={item}
                      active={currentKey === item.key}
                      onClick={() => pick(item.key)}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </nav>

      {onAgentsTab ? (
        <AgentRoster
          focusAgentId={focusAgentId}
          onPick={(id) => {
            onFocusAgent(id);
            onMonitorTabChange('agents');
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
        className={`fixed inset-y-10 left-11 z-30 flex w-56 flex-col overflow-hidden border-r border-white/[0.06] apple-chrome transition-transform md:static md:translate-x-0 ${
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
