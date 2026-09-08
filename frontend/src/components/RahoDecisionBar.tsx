/**
 * 決策阻塞點：L5 用戶可直接點選方案，解除熱馬桶圈。
 */
import { useState } from 'react';
import { decideRaho } from '../api/client';
import type { RahoPendingDecision } from '../types';
import { jumpToRoleDesk, rahoLayerLabel } from '../lib/rahoUi';

interface RahoDecisionBarProps {
  pending: RahoPendingDecision[];
  onResolved?: () => void;
}

export default function RahoDecisionBar({ pending, onResolved }: RahoDecisionBarProps) {
  const [busy, setBusy] = useState<string | null>(null);
  if (!pending.length) return null;

  return (
    <section className="mb-3 rounded-xl border border-[#FF453A]/30 bg-[#FF453A]/8 p-3">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-[#FF453A]">
        決策阻塞點
      </div>
      {pending.map((p) => (
        <div key={p.decision_id} className="mb-3 last:mb-0">
          <p className="text-[13px] text-[#F5F5F7]">{p.question}</p>
          <p className="mt-1 text-[11px] text-[#8E8E93]">
            <button type="button" className="raho-edge-role" onClick={() => jumpToRoleDesk(p.role_id || '')}>
              {p.layer_label || p.role_label || rahoLayerLabel(p.layer)}
            </button>
            {' · '}剩餘 {Math.round(p.remaining_sec ?? 0)}s
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {p.choices.map((c) => (
              <button
                key={c.key}
                type="button"
                disabled={busy === p.decision_id}
                className="rounded-lg border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[11px] text-[#EBEBF5] hover:bg-white/[0.08]"
                onClick={async () => {
                  setBusy(p.decision_id);
                  try {
                    await decideRaho(p.decision_id, c.key);
                    onResolved?.();
                  } finally {
                    setBusy(null);
                  }
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
