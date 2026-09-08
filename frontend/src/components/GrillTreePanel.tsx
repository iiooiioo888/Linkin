/**
 * GrillTreePanel — 遞歸質詢樹：指揮鏈 / 獨立審查 / L0 三條線。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchRahoTree } from '../api/client';
import type { GrillTree, GrillTreeNode, L0Snapshot, RahoGrillEdge, RahoPendingDecision, RahoSnapshot } from '../types';
import {
  COMMAND_CHAIN,
  DIRECTION_LABELS,
  GRILL_EDGES,
  INSPECT_CHAIN,
  KERNEL_CHAIN,
  RAHO_LAYERS,
  directionLabel,
  jumpLayer,
  jumpToRoleDesk,
  kindLabel,
  nodeRoleId,
  nodeRoleLabel,
  openCountForRole,
  rahoTone,
  statusLabel,
} from '../lib/rahoUi';
import L0Panel from './L0Panel';
import { L0BiasHint } from './L0BiasHint';
import RahoDecisionBar from './RahoDecisionBar';

function LayerChip({
  layer,
  directory,
  trees,
  onSelectRole,
  activeRoleId,
}: {
  layer: number;
  directory: typeof RAHO_LAYERS;
  trees: GrillTree[];
  onSelectRole?: (roleId: string) => void;
  activeRoleId?: string;
}) {
  const meta = directory[layer] ?? RAHO_LAYERS[layer];
  const roleId = meta.role_id;
  const open = roleId ? openCountForRole(trees, roleId) : 0;
  const clickable = Boolean(roleId && roleId !== 'user');
  const active = Boolean(roleId && activeRoleId && roleId === activeRoleId);
  return (
    <button
      type="button"
      className={`raho-pyr-item${layer === 0 ? ' is-l0' : ''}${layer === 1 ? ' is-l1' : ''}${active ? ' on' : ''}${clickable ? '' : ' is-static'}`}
      disabled={!clickable}
      onClick={() => {
        if (!clickable || !roleId) return;
        if (onSelectRole && roleId !== 'environment_kernel') {
          onSelectRole(roleId);
          return;
        }
        jumpLayer(layer, roleId);
      }}
      title={clickable ? `開啟 ${meta.full}` : meta.full}
    >
      <span className="raho-pyr-k">{meta.short}</span>
      <span className="raho-pyr-t">{meta.title}</span>
      {open > 0 ? <span className="raho-pyr-n">{open}</span> : null}
    </button>
  );
}

function OrgMap({
  trees,
  directory,
  onSelectRole,
  activeRoleId,
}: {
  trees: GrillTree[];
  directory: typeof RAHO_LAYERS;
  onSelectRole?: (roleId: string) => void;
  activeRoleId?: string;
}) {
  return (
    <div className="raho-org">
      <div className="raho-org-kernel">
        {KERNEL_CHAIN.map((layer) => (
          <LayerChip
            key={layer}
            layer={layer}
            directory={directory}
            trees={trees}
            onSelectRole={onSelectRole}
            activeRoleId={activeRoleId}
          />
        ))}
        <span className="raho-org-hint">滲透 L1–L5，不參與質詢</span>
      </div>
      <div className="raho-org-cols">
        <div className="raho-org-col">
          <div className="raho-org-h">指揮鏈</div>
          <ol className="raho-org-list">
            {COMMAND_CHAIN.map((layer) => (
              <li key={layer}>
                <LayerChip
                  layer={layer}
                  directory={directory}
                  trees={trees}
                  onSelectRole={onSelectRole}
                  activeRoleId={activeRoleId}
                />
              </li>
            ))}
          </ol>
        </div>
        <div className="raho-org-col is-inspect">
          <div className="raho-org-h">獨立審查</div>
          <ol className="raho-org-list">
            {INSPECT_CHAIN.map((layer) => (
              <li key={layer}>
                <LayerChip
                  layer={layer}
                  directory={directory}
                  trees={trees}
                  onSelectRole={onSelectRole}
                  activeRoleId={activeRoleId}
                />
              </li>
            ))}
          </ol>
          <p className="raho-org-note">不隸屬 L3。驗收 L2，規劃缺陷質詢 L3，標準爭議上呈 L4／L5。</p>
        </div>
      </div>
    </div>
  );
}

const LEGEND_ORDER: Array<keyof typeof DIRECTION_LABELS> = ['down', 'up', 'inspect', 'inject'];

function ChainLegend({
  edges,
  onSelectRole,
  focusRoleId,
}: {
  edges: RahoGrillEdge[];
  onSelectRole?: (roleId: string) => void;
  focusRoleId?: string;
}) {
  const pick = (roleId: string) => {
    if (!roleId || roleId === 'user') return;
    if (onSelectRole && roleId !== 'environment_kernel') {
      onSelectRole(roleId);
      return;
    }
    jumpToRoleDesk(roleId);
  };
  return (
    <div className="raho-legend raho-legend--4">
      {LEGEND_ORDER.map((direction) => {
        const group = edges.filter((e) => e.direction === direction);
        if (!group.length) return null;
        return (
          <div key={direction} className="raho-legend-col">
            <div className="raho-legend-h">{directionLabel(direction)}</div>
            <ul>
              {group.map((edge) => (
                <li
                  key={`${edge.from_role}-${edge.to_role}-${edge.kind}-${edge.label}`}
                  className={
                    focusRoleId && (edge.from_role === focusRoleId || edge.to_role === focusRoleId)
                      ? 'on'
                      : undefined
                  }
                >
                  <button
                    type="button"
                    className={`raho-legend-edge${focusRoleId === edge.from_role ? ' on' : ''}`}
                    onClick={() => pick(edge.from_role)}
                  >
                    {edge.from_label}
                  </button>
                  <span>→</span>
                  <button
                    type="button"
                    className={`raho-legend-edge${focusRoleId === edge.to_role ? ' on' : ''}`}
                    onClick={() => pick(edge.to_role)}
                  >
                    {edge.to_label}
                  </button>
                  <span className="raho-legend-k">{edge.label}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}

function RoleJump({
  roleId,
  label,
  onSelectRole,
}: {
  roleId: string;
  label: string;
  onSelectRole?: (roleId: string) => void;
}) {
  if (!roleId || roleId === 'user') {
    return <span>{label}</span>;
  }
  return (
    <button
      type="button"
      className="raho-edge-role"
      onClick={() => {
        if (roleId === 'environment_kernel') {
          jumpLayer(0, roleId);
          return;
        }
        if (onSelectRole) {
          onSelectRole(roleId);
          return;
        }
        jumpToRoleDesk(roleId);
      }}
    >
      {label}
    </button>
  );
}

function GrillEdge({
  node,
  kindLabels,
  onFocus,
  onSelectRole,
  active,
}: {
  node: GrillTreeNode;
  kindLabels?: Record<string, string>;
  onFocus?: (nodeId: string) => void;
  onSelectRole?: (roleId: string) => void;
  active?: boolean;
}) {
  const fromId = nodeRoleId(node, 'from');
  const toId = nodeRoleId(node, 'to');
  return (
    <li className={`raho-edge${active ? ' on' : ''}`}>
      <span className="raho-edge-dot" style={{ background: rahoTone(node.status) }} />
      <div className="min-w-0 flex-1">
        <div className="raho-edge-path">
          <RoleJump roleId={fromId} label={nodeRoleLabel(node, 'from')} onSelectRole={onSelectRole} />
          <span aria-hidden>→</span>
          <RoleJump roleId={toId} label={nodeRoleLabel(node, 'to')} onSelectRole={onSelectRole} />
          <span className="raho-edge-kind">
            {kindLabel(node.kind, kindLabels)} · {statusLabel(node.status)}
          </span>
        </div>
        <button
          type="button"
          className="raho-edge-sum"
          onClick={() => {
            onFocus?.(node.node_id);
          }}
        >
          {node.summary}
        </button>
      </div>
    </li>
  );
}

export default function GrillTreePanel({
  embedded = false,
  focusRoleId = '',
  onSelectRole,
}: {
  embedded?: boolean;
  focusRoleId?: string;
  onSelectRole?: (roleId: string) => void;
} = {}) {
  const [snap, setSnap] = useState<RahoSnapshot>({ trees: [], pending_decisions: [], blocked: [] });
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setSnap(await fetchRahoTree());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void reload();
    const t = setInterval(() => void reload(), 4000);
    return () => clearInterval(t);
  }, [reload]);

  const trees: GrillTree[] = snap.trees ?? [];
  const pending: RahoPendingDecision[] = snap.pending_decisions ?? [];
  const blocked = snap.blocked ?? [];
  const l0: L0Snapshot = snap.l0 ?? {};
  const [detailTab, setDetailTab] = useState<'nodes' | 'l0'>('nodes');
  const [focusNodeId, setFocusNodeId] = useState('');
  const directory = useMemo(() => {
    const next = { ...RAHO_LAYERS };
    for (const row of snap.directory ?? []) {
      next[row.layer] = row;
    }
    return next;
  }, [snap.directory]);

  return (
    <div className={`flex min-h-0 flex-1 flex-col overflow-y-auto ${embedded ? 'px-0 py-0' : 'px-5 py-4'}`}>
      {embedded ? (
        <div className="mb-3 flex items-end justify-between gap-3">
          <p className="text-[12px] text-[#8E8E93]">
            {focusRoleId ? '此角色相關的指揮／審查邊會反白。點層級可切換角色。' : '點層級即可切到對應角色工作台。'}
          </p>
          <button type="button" className="rd-btn text-[11px] text-[#0A84FF]" onClick={() => void reload()}>
            重新整理
          </button>
        </div>
      ) : (
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold text-[#F5F5F7]">遞歸質詢樹</h2>
            <p className="mt-1 text-[12px] text-[#8E8E93]">
              指揮鏈 L5→L4→L3→L2；L1 獨立驗收；L0 滲透。點層級或邊即可跳到對應角色／核心。
            </p>
          </div>
          <button type="button" className="rd-btn text-[11px] text-[#0A84FF]" onClick={() => void reload()}>
            重新整理
          </button>
        </div>
      )}
      {error && <p className="mb-3 text-[12px] text-[#FF453A]">{error}</p>}

      <OrgMap trees={trees} directory={directory} onSelectRole={onSelectRole} activeRoleId={focusRoleId} />
      <ChainLegend
        edges={snap.grill_chain?.length ? snap.grill_chain : GRILL_EDGES}
        onSelectRole={onSelectRole}
        focusRoleId={focusRoleId}
      />
      <L0BiasHint snapshot={l0} compact />
      <RahoDecisionBar pending={pending} onResolved={() => void reload()} />

      <div className="l0-tabs mb-3" role="tablist">
        <button type="button" className={`l0-tab${detailTab === 'nodes' ? ' on' : ''}`} onClick={() => setDetailTab('nodes')}>
          節點明細
        </button>
        <button type="button" className={`l0-tab${detailTab === 'l0' ? ' on' : ''}`} onClick={() => setDetailTab('l0')}>
          知識與記憶
        </button>
      </div>

      {detailTab === 'l0' ? (
        <L0Panel snapshot={l0} embed query={trees[0]?.goal || ''} nodeId={focusNodeId} initialTab="memory" />
      ) : null}

      {detailTab === 'nodes' && trees.length === 0 && blocked.length === 0 && pending.length === 0 && (
        <p className="py-16 text-center text-[13px] text-[#636366]">尚無質詢鏈。複雜任務啟動後會在此展開。</p>
      )}

      {detailTab === 'nodes' ? <div className="space-y-4">
        {trees.map((tree) => (
          <article key={tree.tree_id} className="rounded-xl border border-white/[0.06] bg-[#1C1C1E] p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <div className="text-[12px] text-[#8E8E93]">run {tree.run_id.slice(0, 8)}</div>
                <div className="text-[13px] text-[#F5F5F7]">{tree.goal || '（戰役）'}</div>
              </div>
              {tree.open_count > 0 && (
                <span className="rounded-full bg-[#FF453A]/15 px-2 py-0.5 text-[10px] text-[#FF453A]">
                  {tree.open_count} 處阻塞
                </span>
              )}
            </div>
            {(tree.campaign?.nodes?.length ?? 0) > 0 && (
              <ol className="mb-3 flex flex-wrap gap-1.5">
                {tree.campaign!.nodes!.map((node) => (
                  <li key={node.node_id}>
                    <button
                      type="button"
                      className={`rounded-md border px-2 py-1 text-[10px] ${
                        focusNodeId === node.node_id
                          ? 'border-[#64D2FF] bg-[#64D2FF]/10 text-[#F5F5F7]'
                          : 'border-white/10 bg-white/[0.03] text-[#AEAEB2]'
                      }`}
                      title={node.success_criteria}
                      onClick={() => {
                        setFocusNodeId(node.node_id);
                        setDetailTab('l0');
                      }}
                    >
                      {node.node_id} {node.title}
                      {node.depends_on?.length ? ` ← ${node.depends_on.join(',')}` : ''}
                    </button>
                  </li>
                ))}
              </ol>
            )}
            <ol className="space-y-2">
              {tree.nodes.map((node) => (
                <GrillEdge
                  key={node.node_id}
                  node={node}
                  kindLabels={snap.kind_labels}
                  onSelectRole={onSelectRole}
                  active={
                    Boolean(focusRoleId) &&
                    (nodeRoleId(node, 'from') === focusRoleId || nodeRoleId(node, 'to') === focusRoleId)
                  }
                  onFocus={(id) => {
                    setFocusNodeId(id);
                    setDetailTab('l0');
                  }}
                />
              ))}
            </ol>
          </article>
        ))}
      </div> : null}

      {embedded ? null : (
        <p className="mt-6 text-center text-[11px] text-[#636366]">
          指揮鏈點層級開工作台；L1 開憲兵；L0 開環境與記憶核心。
        </p>
      )}
    </div>
  );
}
