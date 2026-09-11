/**
 * 決策阻塞點：L5 用戶可直接點選方案。
 * 畫在文件流內（工作台標題區／抽屜），不用 portal，避免被底欄或遮罩擋住點擊。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { decideRaho, fetchRahoTree } from '../api/client';
import type { RahoPendingDecision } from '../types';
import { jumpToRoleDesk, rahoLayerLabel } from '../lib/rahoUi';

interface RahoDecisionBarProps {
  pending?: RahoPendingDecision[];
  /** 有值時輪詢 /raho/tree，確保等待期間也能點選 */
  runId?: string;
  poll?: boolean;
  /**
   * chat：對話工作台（文件流內，可點）
   * embed：任務卡／質詢樹內嵌
   */
  variant?: 'chat' | 'embed';
  onResolved?: (decisionId?: string) => void;
  /** 有待決時通知外層（例如關閉手機側欄遮罩） */
  onPendingChange?: (hasPending: boolean) => void;
}

function remainingOf(p: RahoPendingDecision, nowMs: number): number {
  if (typeof p.created_at === 'number' && typeof p.ttl === 'number') {
    return Math.max(0, p.ttl - (nowMs / 1000 - p.created_at));
  }
  return Math.max(0, Number(p.remaining_sec ?? 0));
}

/** 只要後端仍列為待決（未 resolved），就允許點選；剩餘 0s 仍可裁決。 */
function isActionable(p: RahoPendingDecision): boolean {
  if (p.resolved) return false;
  if (!p.decision_id) return false;
  if ((p.choices?.length ?? 0) === 0) return false;
  return true;
}

function mergePending(
  live: RahoPendingDecision[] | null,
  prop: RahoPendingDecision[],
  liveReady: boolean,
): RahoPendingDecision[] {
  if (liveReady && live !== null) return live;
  return prop;
}

function choiceKey(c: { key?: string; label?: string }, idx: number): string {
  return String(c.key || c.label || idx);
}

export default function RahoDecisionBar({
  pending: pendingProp,
  runId,
  poll = false,
  variant = 'embed',
  onResolved,
  onPendingChange,
}: RahoDecisionBarProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<RahoPendingDecision[] | null>(null);
  const [liveReady, setLiveReady] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const decidingRef = useRef(false);

  const propList = pendingProp ?? [];
  const shouldPoll = poll || propList.some(isActionable);

  useEffect(() => {
    if (!shouldPoll) {
      setLive(null);
      setLiveReady(false);
      return;
    }
    let cancelled = false;
    const tick = async () => {
      try {
        const snap = await fetchRahoTree();
        if (cancelled) return;
        let next = snap.pending_decisions ?? [];
        if (runId) {
          const filtered = next.filter((p) => p.run_id === runId);
          // runId 對不上時勿清空：保留全域待決
          next = filtered.length > 0 ? filtered : next;
        }
        setLive(next);
        setLiveReady(true);
      } catch {
        // 輪詢失敗不蓋掉既有 prop
      }
    };
    void tick();
    const t = setInterval(() => void tick(), 1200);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [shouldPoll, runId]);

  const pending = mergePending(live, propList, liveReady);
  const actionable = useMemo(() => pending.filter(isActionable), [pending]);

  useEffect(() => {
    onPendingChange?.(actionable.length > 0);
  }, [actionable.length, onPendingChange]);

  useEffect(() => {
    if (!actionable.length) return;
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [actionable.length]);

  const dropDecision = useCallback(
    (decisionId: string) => {
      setLive((prev) => (prev ?? pending).filter((x) => x.decision_id !== decisionId));
      setLiveReady(true);
      onResolved?.(decisionId);
    },
    [onResolved, pending],
  );

  const pickChoice = useCallback(
    async (decisionId: string, choiceKeyValue: string) => {
      if (decidingRef.current) return;
      if (!choiceKeyValue) {
        setError('此方案缺少 choice key，無法送出裁決');
        return;
      }
      decidingRef.current = true;
      setBusy(decisionId);
      setError(null);
      try {
        await decideRaho(decisionId, choiceKeyValue);
        dropDecision(decisionId);
      } catch (err) {
        const msg = (err as Error).message || '裁決失敗';
        // 已逾時自動裁決／重複點選：清掉幽靈列
        if (/不存在|已裁決|已解決|404|timeout|逾時/.test(msg)) {
          dropDecision(decisionId);
          setError(`${msg}（已自列表移除；若任務仍停住請稍候自動繼續）`);
        } else {
          setError(msg);
        }
      } finally {
        decidingRef.current = false;
        setBusy(null);
      }
    },
    [dropDecision],
  );

  if (!actionable.length) return null;

  return (
    <section
      className={`raho-decision-bar relative z-[80] rounded-xl border border-[#FF453A]/40 bg-[#1C0B0A] p-3 shadow-lg pointer-events-auto ${
        variant === 'chat' ? 'mb-0' : 'mb-3'
      }`}
      role="region"
      aria-label="決策阻塞點"
      data-testid="raho-decision-bar"
      data-variant={variant}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-[11px] font-medium uppercase tracking-wide text-[#FF453A]">
          決策阻塞點
        </div>
        <p className="text-[10px] text-[#8E8E93]">點選下方方案以繼續任務</p>
      </div>
      {error && (
        <p
          className="mb-2 rounded-md border border-[#FF453A]/30 bg-[#FF453A]/10 px-2 py-1.5 text-[11px] text-[#FF453A]"
          role="alert"
        >
          {error}
        </p>
      )}
      {actionable.map((p) => {
        const remain = Math.round(remainingOf(p, nowMs));
        const expired = remain <= 0;
        return (
          <div key={p.decision_id} className="mb-3 last:mb-0">
            <p className="whitespace-pre-wrap text-[13px] text-[#F5F5F7]">{p.question}</p>
            <p className="mt-1 text-[11px] text-[#8E8E93]">
              <button
                type="button"
                className="raho-edge-role"
                onClick={() => jumpToRoleDesk(p.role_id || '')}
              >
                {p.layer_label || p.role_label || rahoLayerLabel(p.layer)}
              </button>
              {' · '}
              {expired ? (
                <span className="text-[#FF9F0A]">等待裁決（計時已盡，仍可點選）</span>
              ) : (
                <>剩餘 {remain}s</>
              )}
            </p>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              {p.choices.map((c, idx) => {
                const key = choiceKey(c, idx);
                const choice = String(c.key || '');
                return (
                  <button
                    key={key}
                    type="button"
                    disabled={busy === p.decision_id}
                    className="raho-decision-choice relative z-[81] w-full cursor-pointer touch-manipulation rounded-lg border border-[var(--console-line)] bg-[color-mix(in_srgb,var(--console-ink)_8%,transparent)] px-3 py-2.5 text-left text-[13px] font-medium text-[var(--console-ink)] hover:border-[color-mix(in_srgb,var(--console-blue)_40%,transparent)] hover:bg-[color-mix(in_srgb,var(--console-blue)_12%,transparent)] active:scale-[0.99] disabled:cursor-wait disabled:opacity-50 sm:w-auto sm:min-w-[10rem]"
                    onClick={(ev) => {
                      ev.preventDefault();
                      ev.stopPropagation();
                      void pickChoice(p.decision_id, choice);
                    }}
                  >
                    {c.label || c.key}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </section>
  );
}
