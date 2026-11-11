/**
 * 整合面板 Ouroboros 訪談／auto／評估動作區。
 */
import { useState } from 'react';
import { ouroborosAuto, ouroborosEvaluate, ouroborosInterview } from '../../api/integrations';
import { btnCls, btnPrimaryCls, inputCls } from './helpers';
import { ErrorBar, JsonBlock, OkBar } from './shared';

export function OuroborosActions() {
  const [goal, setGoal] = useState('');
  const [ambiguity, setAmbiguity] = useState('0.15');
  const [force, setForce] = useState(false);
  const [executionId, setExecutionId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [payload, setPayload] = useState<unknown>(null);

  const run = async (fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const out = await fn();
      setPayload(out);
      const obj = out as { ok?: boolean; allowed?: boolean; error_code?: string };
      if (obj.ok === false || obj.allowed === false) {
        setError(obj.error_code || '閘門阻擋或失敗');
      } else {
        setMessage(okMsg);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <ErrorBar message={error} />
      <OkBar message={message} />
      <label className="block text-[10px] text-[var(--console-sub)]">
        目標 goal
        <textarea className={`${inputCls} mt-1 min-h-[56px]`} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="block text-[10px] text-[var(--console-sub)]">
          ambiguity（≤0.2 才准 Seed）
          <input className={`${inputCls} mt-1 w-28`} value={ambiguity} onChange={(e) => setAmbiguity(e.target.value)} />
        </label>
        <label className="flex items-center gap-1.5 pb-1 text-[11px] text-[var(--console-sub)]">
          <input type="checkbox" className="accent-[var(--console-accent)]" checked={force} onChange={(e) => setForce(e.target.checked)} />
          force 繞過閘門
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={btnCls}
          disabled={busy || !goal.trim()}
          onClick={() => void run(() => ouroborosInterview(goal.trim()), '訪談完成')}
        >
          訪談
        </button>
        <button
          type="button"
          className={btnPrimaryCls}
          disabled={busy || !goal.trim()}
          onClick={() =>
            void run(
              () =>
                ouroborosAuto({
                  goal: goal.trim(),
                  ambiguity: Number(ambiguity) || 0,
                  force,
                }),
              'auto 已啟動',
            )
          }
        >
          啟動 auto
        </button>
      </div>
      <label className="block text-[10px] text-[var(--console-sub)]">
        execution_id（評估）
        <input className={`${inputCls} mt-1`} value={executionId} onChange={(e) => setExecutionId(e.target.value)} />
      </label>
      <button
        type="button"
        className={btnCls}
        disabled={busy || !executionId.trim()}
        onClick={() => void run(() => ouroborosEvaluate(executionId.trim()), '三階段評估完成')}
      >
        執行評估
      </button>
      <JsonBlock value={payload} />
    </div>
  );
}
