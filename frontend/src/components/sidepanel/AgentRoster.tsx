/**
 * SidePanel 角色名冊（虛擬滾動＋搜尋／篩選）。
 */
import { useMemo, useRef, useState } from 'react';
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso';
import {
  agentOpenCount,
  dispatchJumpAgent,
  filterAgentsByDesk,
  isAlertAgent,
  isLiveAgent,
  type AgentDeskScope,
} from '../../lib/agentUi';
import { AGENT_FALLBACK_ROSTER } from '../../lib/monitorFallbacks';
import { agentRahoLabel } from '../../lib/rahoUi';
import { useMonitorStore } from '../../stores/monitorStore';
import type { RoleAgent } from '../../types';

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

export function AgentRoster({
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
    const hiddenRoleIds = new Set(['constitutional_inspector', 'environment_kernel']);
    for (const lv of ORG_LEVELS) {
      const list = filtered.filter((a) => a.level === lv.level && !hiddenRoleIds.has(a.id));
      if (!list.length) continue;
      out.push({ kind: 'header', key: `h-${lv.level}`, label: lv.label, count: list.length });
      for (const agent of list) {
        out.push({ kind: 'agent', key: agent.id, agent });
      }
    }
    return out;
  }, [filtered]);

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
        <span className="ar-ht">{deskScope === 'studio' ? '工作室' : '組織'}</span>
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
          <p className="text-[12px] text-[var(--console-sub)]">
            {searching ? '沒有符合搜尋的角色' : scope === 'alert' ? '目前沒有告警' : scope === 'live' ? '目前沒有限定角色' : '尚無名冊'}
          </p>
          {(scope !== 'all' || searching) && (
            <button
              type="button"
              onClick={clearFilters}
              className="mt-2 text-[11px] text-[var(--console-accent)] hover:underline"
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
                  if (!staticRow) onPick(row.key);
                }}
                className="ar-ri"
              >
                <span className={`ar-dot ${row.layer === 0 ? 'wait' : ''}`} />
                <span className="min-w-0 flex-1 truncate">
                  {row.short}
                  <span className="ml-1 text-[9px] text-[var(--console-sub)]">{row.label}</span>
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
                <span className="ml-1 text-[9px] text-[var(--console-sub)]">{agentRahoLabel(agent)}</span>
                {agent.enabled === false ? <span className="ml-1 text-[9px] text-[var(--console-danger)]">停</span> : null}
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
