/**
 * GrillTreePanel — 遞歸質詢樹：L5→L2 質詢鏈與決策阻塞點。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchRahoTree } from '../api/client';
import type { GrillTree, RahoPendingDecision, RahoSnapshot } from '../types';
import RahoDecisionBar from './RahoDecisionBar';

const LAYER: Record<number, string> = {
  1: 'L1 憲兵',
  2: 'L2 執行',
  3: 'L3 指揮',
  4: 'L4 規劃',
  5: 'L5 用戶',
};

function statusTone(status: string): string {
  if (status === 'blocked' || status === 'open') return 'var(--apple-red)';
  if (status === 'timeout') return 'var(--apple-orange, #FF9F0A)';
  if (status === 'escalated') return '#BF5AF2';
  return 'var(--apple-green)';
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

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold text-[#F5F5F7]">遞歸質詢樹</h2>
          <p className="mt-1 text-[12px] text-[#8E8E93]">
            紅點為尚未解決的決策阻塞。下層可向上烤問，逾時則熱馬桶圈跳級至你。
          </p>
        </div>
        <button type="button" className="rd-btn text-[11px] text-[#0A84FF]" onClick={() => void reload()}>
          重新整理
        </button>
      </div>
      {error && <p className="mb-3 text-[12px] text-[#FF453A]">{error}</p>}

      <RahoDecisionBar pending={pending} onResolved={() => void reload()} />

      {trees.length === 0 && blocked.length === 0 && pending.length === 0 && (
        <p className="py-16 text-center text-[13px] text-[#636366]">尚無質詢鏈。複雜任務啟動後會在此展開。</p>
      )}

      <div className="space-y-4">
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
                  <li
                    key={node.node_id}
                    className="rounded-md border border-white/10 bg-white/[0.03] px-2 py-1 text-[10px] text-[#AEAEB2]"
                    title={node.success_criteria}
                  >
                    {node.node_id} {node.title}
                    {node.depends_on?.length ? ` ← ${node.depends_on.join(',')}` : ''}
                  </li>
                ))}
              </ol>
            )}
            <ol className="space-y-2">
              {tree.nodes.map((node) => (
                <li key={node.node_id} className="flex gap-3">
                  <span
                    className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                    style={{ background: statusTone(node.status) }}
                  />
                  <div className="min-w-0">
                    <div className="text-[11px] text-[#8E8E93]">
                      {LAYER[node.from_layer] ?? `L${node.from_layer}`} → {LAYER[node.to_layer] ?? `L${node.to_layer}`}
                      {' · '}
                      {node.kind} · {node.status}
                    </div>
                    <p className="text-[12px] text-[#EBEBF5]">{node.summary}</p>
                  </div>
                </li>
              ))}
            </ol>
          </article>
        ))}
      </div>
    </div>
  );
}
