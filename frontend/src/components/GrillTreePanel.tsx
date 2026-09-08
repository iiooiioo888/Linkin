/**
 * GrillTreePanel — 遞歸質詢樹：與角色名冊共用 L0–L5 身分。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchRahoTree } from '../api/client';
import type { GrillTree, GrillTreeNode, L0Snapshot, RahoPendingDecision, RahoSnapshot } from '../types';
import {
  RAHO_CHAIN,
  RAHO_LAYERS,
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
import RahoDecisionBar from './RahoDecisionBar';

function Pyramid({
  trees,
  directory,
}: {
  trees: GrillTree[];
  directory: typeof RAHO_LAYERS;
}) {
  return (
    <ol className="raho-pyramid">
      {RAHO_CHAIN.map((layer) => {
        const meta = directory[layer] ?? RAHO_LAYERS[layer];
        const roleId = meta.role_id;
        const open = roleId ? openCountForRole(trees, roleId) : 0;
        const clickable = Boolean(roleId && roleId !== 'user');
        return (
          <li key={layer}>
            <button
              type="button"
              className={`raho-pyr-item${layer === 0 ? ' is-l0' : ''}${clickable ? '' : ' is-static'}`}
              disabled={!clickable}
              onClick={() => clickable && jumpLayer(layer, roleId)}
              title={clickable ? `開啟 ${meta.full}` : meta.full}
            >
              <span className="raho-pyr-k">{meta.short}</span>
              <span className="raho-pyr-t">{meta.title}</span>
              {open > 0 ? <span className="raho-pyr-n">{open}</span> : null}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

function RoleJump({ roleId, label }: { roleId: string; label: string }) {
  if (!roleId || roleId === 'user') {
    return <span>{label}</span>;
  }
  return (
    <button type="button" className="raho-edge-role" onClick={() => jumpToRoleDesk(roleId)}>
      {label}
    </button>
  );
}

function GrillEdge({
  node,
  kindLabels,
}: {
  node: GrillTreeNode;
  kindLabels?: Record<string, string>;
}) {
  const fromId = nodeRoleId(node, 'from');
  const toId = nodeRoleId(node, 'to');
  return (
    <li className="raho-edge">
      <span className="raho-edge-dot" style={{ background: rahoTone(node.status) }} />
      <div className="min-w-0 flex-1">
        <div className="raho-edge-path">
          <RoleJump roleId={fromId} label={nodeRoleLabel(node, 'from')} />
          <span aria-hidden>→</span>
          <RoleJump roleId={toId} label={nodeRoleLabel(node, 'to')} />
          <span className="raho-edge-kind">
            {kindLabel(node.kind, kindLabels)} · {statusLabel(node.status)}
          </span>
        </div>
        <p className="raho-edge-sum">{node.summary}</p>
      </div>
    </li>
  );
}

export default function GrillTreePanel() {
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
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold text-[#F5F5F7]">遞歸質詢樹</h2>
          <p className="mt-1 text-[12px] text-[#8E8E93]">
            與角色工作台同一套 L0–L5 身分。點層級或邊即可跳到對應角色／L0 核心。
          </p>
        </div>
        <button type="button" className="rd-btn text-[11px] text-[#0A84FF]" onClick={() => void reload()}>
          重新整理
        </button>
      </div>
      {error && <p className="mb-3 text-[12px] text-[#FF453A]">{error}</p>}

      <Pyramid trees={trees} directory={directory} />
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
                <GrillEdge key={node.node_id} node={node} kindLabels={snap.kind_labels} />
              ))}
            </ol>
          </article>
        ))}
      </div> : null}

      <p className="mt-6 text-center text-[11px] text-[#636366]">
        點金字塔或質詢邊，即可開啟對應角色工作台；L0 開啟環境與記憶核心。
      </p>
    </div>
  );
}
