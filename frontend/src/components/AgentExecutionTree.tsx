/**
 * AgentExecutionTree — 角色監控上的本地執行樹。
 * 視覺對齊監控儀表板 v3（金 #c9a961／#6e5a32，底 #08080a）。
 * 不依賴 @affectui/agent-tree 或任何 Pro 授權。
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ancestorOpenIds,
  branchIds,
  buildAgentExecutionTree,
  defaultOpenIds,
  filterAgentTree,
  focusAgentTree,
  summarizeAgentTree,
  type AgentTreeFocus,
  type AgentTreeNode,
  type AgentTreeSummary,
} from '../lib/agentTree';
import type { RoleAgent } from '../types';
import './ui/monitor/monitor.css';

interface AgentExecutionTreeProps {
  agents: RoleAgent[];
  selectedId?: string | null;
  generatedAt?: string | null;
  onSelectRole: (id: string) => void;
  onSelectWork?: (roleId: string) => void;
}

function preferOpenPanel(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true;
  return !window.matchMedia('(max-width: 767px)').matches;
}

function formatClock(iso?: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('zh-TW', { hour12: false });
}

function summaryLine(summary: AgentTreeSummary): string {
  const bits = [`共 ${summary.roles} 席`];
  if (summary.running) bits.push(`${summary.running} 執行中`);
  if (summary.waiting) bits.push(`${summary.waiting} 等待`);
  if (summary.failed) bits.push(`${summary.failed} 阻塞`);
  if (summary.disabled) bits.push(`${summary.disabled} 停用`);
  if (!summary.running && !summary.waiting && !summary.failed && summary.idle === summary.roles && summary.roles > 0) {
    bits.push('全部待命');
  }
  if (summary.work) bits.push(`${summary.work} 項進行中`);
  return bits.join(' · ');
}

function TreeBranch({
  nodes,
  openIds,
  forceOpen,
  selectedId,
  onToggle,
  onSelectRole,
  onSelectWork,
}: {
  nodes: AgentTreeNode[];
  openIds: Set<string>;
  forceOpen: boolean;
  selectedId?: string | null;
  onToggle: (id: string) => void;
  onSelectRole: (id: string) => void;
  onSelectWork?: (roleId: string) => void;
}) {
  return (
    <>
      {nodes.map((node) => {
        const branch = node.kind === 'role' && node.children.length > 0;
        const open = branch && (forceOpen || openIds.has(node.id));
        const selected = node.kind === 'role' && node.roleId === selectedId;
        return (
          <div key={node.id} className="agent-tree-item">
            <div
              className={`agent-tree-row${selected ? ' is-selected' : ''}${node.kind === 'work' ? ' agent-tree-row--work' : ''}`}
              role="treeitem"
              aria-expanded={branch ? open : undefined}
              aria-selected={node.kind === 'role' ? selected : undefined}
              data-role-id={node.kind === 'role' ? node.roleId : undefined}
            >
              {branch ? (
                <button
                  type="button"
                  className={`agent-tree-twist${open ? ' is-open' : ''}`}
                  aria-label={open ? `收合 ${node.label}` : `展開 ${node.label}`}
                  onClick={() => onToggle(node.id)}
                >
                  <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden>
                    <path d="M3.2 1.6 L7 5 L3.2 8.4" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </button>
              ) : (
                <span className="agent-tree-twist agent-tree-twist--spacer" aria-hidden />
              )}
              <button
                type="button"
                className="agent-tree-main"
                title={`${node.label} · ${node.statusLabel}${node.hint ? ` · ${node.hint}` : ''}`}
                onClick={() => {
                  if (node.kind === 'work') onSelectWork?.(node.roleId);
                  else onSelectRole(node.roleId);
                }}
              >
                <span className={`agent-tree-dot agent-tree-dot--${node.status}`} aria-hidden />
                <span className="agent-tree-name">{node.label}</span>
                {node.hint ? <span className="agent-tree-hint">{node.hint}</span> : null}
                <span className={`agent-tree-chip agent-tree-chip--${node.status}`}>{node.statusLabel}</span>
              </button>
            </div>
            {open ? (
              <div className="agent-tree-group" role="group">
                <TreeBranch
                  nodes={node.children}
                  openIds={openIds}
                  forceOpen={forceOpen}
                  selectedId={selectedId}
                  onToggle={onToggle}
                  onSelectRole={onSelectRole}
                  onSelectWork={onSelectWork}
                />
              </div>
            ) : null}
          </div>
        );
      })}
    </>
  );
}

export default function AgentExecutionTree({
  agents,
  selectedId,
  generatedAt,
  onSelectRole,
  onSelectWork,
}: AgentExecutionTreeProps) {
  const tree = useMemo(() => buildAgentExecutionTree(agents), [agents]);
  const summary = useMemo(() => summarizeAgentTree(tree), [tree]);
  const [query, setQuery] = useState('');
  const [focus, setFocus] = useState<AgentTreeFocus>('all');
  const [panelOpen, setPanelOpen] = useState(preferOpenPanel);
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(defaultOpenIds(tree)));
  const known = useRef<Set<string> | null>(null);
  const liveSeen = useRef<Set<string>>(new Set());
  const selectedPath = useRef<string>('');
  const rootRef = useRef<HTMLElement>(null);
  if (known.current === null) known.current = new Set(branchIds(tree));

  const visible = useMemo(
    () => focusAgentTree(filterAgentTree(tree, query), focus),
    [tree, query, focus],
  );
  const forceOpen = Boolean(query.trim()) || focus === 'live';
  const clock = formatClock(generatedAt);

  useEffect(() => {
    const defaults = new Set(defaultOpenIds(tree));
    const liveNow = new Set<string>();
    const newlyKnown: string[] = [];
    const visit = (nodes: AgentTreeNode[]) => {
      for (const node of nodes) {
        if (node.kind !== 'role') continue;
        if (node.status === 'running' || node.status === 'waiting' || node.status === 'failed') liveNow.add(node.id);
        if (!known.current?.has(node.id)) newlyKnown.push(node.id);
        visit(node.children);
      }
    };
    visit(tree);

    const toOpen = new Set<string>();
    for (const id of newlyKnown) {
      known.current?.add(id);
      if (defaults.has(id)) toOpen.add(id);
    }
    for (const id of liveNow) {
      if (!liveSeen.current.has(id)) toOpen.add(id);
    }
    liveSeen.current = liveNow;
    if (!toOpen.size) return;

    setOpenIds((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const id of toOpen) {
        if (!next.has(id)) {
          next.add(id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [tree]);

  useEffect(() => {
    if (!selectedId) return;
    const extra = ancestorOpenIds(tree, selectedId);
    const signature = `${selectedId}:${extra.join('|')}`;
    if (selectedPath.current === signature) return;
    selectedPath.current = signature;
    if (!extra.length) return;
    setOpenIds((prev) => {
      const next = new Set(prev);
      let changed = false;
      for (const id of extra) {
        if (!next.has(id)) {
          next.add(id);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [selectedId, tree]);

  useEffect(() => {
    if (!panelOpen || !selectedId) return;
    const root = rootRef.current;
    if (!root) return;
    const escaped = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(selectedId) : selectedId;
    const row = root.querySelector(`[data-role-id="${escaped}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }, [selectedId, panelOpen, visible]);

  const toggle = (id: string) => {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setOpenIds(new Set(branchIds(tree)));
  const collapseAll = () => setOpenIds(new Set());

  return (
    <section
      ref={rootRef}
      className={`agent-exec-tree${panelOpen ? '' : ' is-collapsed'}`}
      data-monitor="agent-execution-tree"
      aria-label="角色執行狀態"
    >
      <header className="agent-exec-tree__head">
        <div className="agent-exec-tree__title-block">
          <h2 className="agent-exec-tree__title">角色執行狀態</h2>
          <p className="agent-exec-tree__summary">
            {summary.roles === 0 ? '尚無角色' : summaryLine(summary)}
            {clock ? <span className="agent-exec-tree__clock">更新 {clock}</span> : null}
          </p>
        </div>
        <div className="agent-exec-tree__actions">
          <button type="button" className="agent-tree-textbtn" onClick={expandAll} disabled={!panelOpen || summary.roles === 0}>
            全部展開
          </button>
          <button type="button" className="agent-tree-textbtn" onClick={collapseAll} disabled={!panelOpen || summary.roles === 0}>
            全部收合
          </button>
          <button
            type="button"
            className="agent-tree-textbtn agent-tree-textbtn--accent"
            aria-expanded={panelOpen}
            onClick={() => setPanelOpen((open) => !open)}
          >
            {panelOpen ? '收合' : '展開'}
          </button>
        </div>
      </header>

      {panelOpen ? (
        <>
          <div className="agent-exec-tree__tools">
            <label className="agent-tree-search-wrap">
              <span className="agent-tree-sr">篩選角色或工作</span>
              <input
                className="agent-tree-search"
                value={query}
                placeholder="篩選角色或工作"
                onChange={(event) => setQuery(event.target.value)}
                spellCheck={false}
                autoComplete="off"
              />
            </label>
            <button
              type="button"
              className={`agent-tree-textbtn${focus === 'live' ? ' is-on' : ''}`}
              aria-pressed={focus === 'live'}
              onClick={() => setFocus((current) => (current === 'live' ? 'all' : 'live'))}
            >
              {focus === 'live' ? '顯示全部' : '只看有動作'}
            </button>
          </div>
          <div className="agent-exec-tree__body" role="tree">
            {visible.length === 0 ? (
              <p className="agent-tree-empty">
                {summary.roles === 0 ? '名冊是空的。後端恢復後會自動帶入角色。' : '沒有符合的角色或進行中工作。'}
              </p>
            ) : (
              <TreeBranch
                nodes={visible}
                openIds={openIds}
                forceOpen={forceOpen}
                selectedId={selectedId}
                onToggle={toggle}
                onSelectRole={onSelectRole}
                onSelectWork={onSelectWork}
              />
            )}
          </div>
        </>
      ) : null}
    </section>
  );
}
