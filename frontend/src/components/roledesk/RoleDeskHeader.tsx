/**
 * 角色工作台標題列：角色切換選單、RAHO／組織標籤與工作台分頁按鈕。
 */

import { useMemo, useState, type ReactNode } from 'react';
import type { RoleAgent } from '../../types';
import { agentRahoLabel, orgLevelCaption } from '../../lib/rahoUi';
import { roleInitials } from './shared';
import type { RoleDeskTab } from './types';

export function RoleDeskHeader({
  agent,
  agents,
  modelLabel,
  deskTab,
  onDeskTab,
  onSelectAgent,
  extra,
  showQuant,
}: {
  agent: RoleAgent;
  agents?: RoleAgent[];
  modelLabel?: string;
  deskTab: RoleDeskTab;
  onDeskTab: (tab: RoleDeskTab) => void;
  onSelectAgent?: (id: string) => void;
  extra?: ReactNode;
  showQuant?: boolean;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const open = agent.executing + agent.queue;
  const grouped = useMemo(() => {
    if (!agents?.length) return [];
    const groups = new Map<string, RoleAgent[]>();
    for (const a of agents) {
      const key = a.raho_short || a.level_label || `L${a.level}`;
      const list = groups.get(key) ?? [];
      list.push(a);
      groups.set(key, list);
    }
    return [...groups.entries()].sort((a, b) => {
      const la = a[1][0]?.raho_layer ?? a[1][0]?.level ?? 99;
      const lb = b[1][0]?.raho_layer ?? b[1][0]?.level ?? 99;
      return lb - la;
    });
  }, [agents]);

  return (
    <div className="rd-header">
      <div className="rd-id">
        <div className="relative">
          <button
            type="button"
            className="rd-av"
            onClick={() => agents?.length ? setPickerOpen((v) => !v) : undefined}
            title={agents?.length ? '切換角色' : undefined}
          >
            {roleInitials(agent.name)}
          </button>
          {pickerOpen && agents?.length ? (
            <>
              <button
                type="button"
                className="fixed inset-0 z-40 cursor-default"
                aria-label="關閉角色選單"
                onClick={() => setPickerOpen(false)}
              />
              <div className="absolute left-0 top-full z-50 mt-1 max-h-72 w-64 overflow-y-auto rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)] shadow-xl">
                {grouped.map(([group, list]) => (
                  <div key={group} className="border-b border-[var(--console-line)] last:border-0">
                    <p className="px-3 py-1.5 text-[8px] font-semibold text-[var(--console-faint)]">
                      {group}
                    </p>
                    {list.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        className={`flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] hover:bg-[var(--console-card)] ${
                          a.id === agent.id ? 'text-[var(--console-accent)]' : 'text-[var(--console-ink)]'
                        }`}
                        onClick={() => {
                          onSelectAgent?.(a.id);
                          setPickerOpen(false);
                        }}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${a.status === 'busy' ? 'bg-[var(--console-green)]' : 'bg-[var(--console-dim)]'}`} />
                        <span className="truncate">{a.name}</span>
                        {a.executing > 0 ? (
                          <span className="ml-auto font-mono text-[9px] text-[var(--console-blue)]">{a.executing}</span>
                        ) : null}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="rd-name">{agent.name}</h1>
            {agent.raho_short ? (
              <button
                type="button"
                className="rounded border border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-1.5 py-0.5 text-[9px] font-semibold text-[var(--console-accent)]"
                onClick={() => agents?.length && setPickerOpen((v) => !v)}
              >
                {agent.raho_short}
              </button>
            ) : null}
          </div>
          <div className="rd-tags">
            <span className="rd-tag rd-tag--raho">{agentRahoLabel(agent)}</span>
            <span className="rd-tag rd-tag--muted">{orgLevelCaption(agent)}</span>
            <span className="rd-tag rd-tag--ok">序列 {agent.queue}</span>
            <span className="rd-tag rd-tag--ok">執行 {agent.executing}</span>
            {agent.max_output_tokens ? (
              <span className="rd-tag rd-tag--muted">推理 {agent.max_output_tokens.toLocaleString()} tok</span>
            ) : null}
            {modelLabel ? <span className="rd-tag rd-tag--muted">{modelLabel}</span> : null}
            {agent.on_call ? <span className="rd-tag">值班</span> : null}
            {agent.enabled === false ? <span className="rd-tag rd-tag--err">停用</span> : null}
            {agent.demoted || agent.metrics?.demoted ? (
              <span className="rd-tag rd-tag--err">規劃已降級</span>
            ) : agent.raho_rank === 'watch' || agent.metrics?.raho_rank === 'watch' ? (
              <span className="rd-tag">被質詢偏高</span>
            ) : null}
          </div>
        </div>
      </div>
      <div className="rd-acts">
        {extra}
        {showQuant ? (
          <button
            type="button"
            className={`rd-btn ${deskTab === 'quant' ? 'on' : ''}`}
            onClick={() => onDeskTab('quant')}
          >
            策略庫
          </button>
        ) : null}
        <button
          type="button"
          className={`rd-btn ${deskTab === 'monitor' ? 'on' : ''}`}
          onClick={() => onDeskTab('monitor')}
        >
          監控
        </button>
        <button
          type="button"
          className={`rd-btn ${deskTab === 'settings' ? 'on' : ''}`}
          onClick={() => onDeskTab('settings')}
        >
          設定
        </button>
        <button
          type="button"
          className={`rd-btn ${deskTab === 'list' ? 'on' : ''}`}
          onClick={() => onDeskTab('list')}
        >
          任務列表{(agent.company_tasks?.length ?? 0) > 0 ? ` ${agent.company_tasks?.length}` : ''}
        </button>
        <button
          type="button"
          className={`rd-btn ${deskTab === 'tasks' ? 'rd-btn-p' : ''}`}
          onClick={() => onDeskTab('tasks')}
        >
          工作台{open > 0 ? ` ${open}` : ''}
        </button>
      </div>
    </div>
  );
}
