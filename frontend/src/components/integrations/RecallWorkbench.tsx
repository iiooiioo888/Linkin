/**
 * 整合面板召回試跑工作台（MemOS＋OpenViking＋WeKnora）。
 */
import { useState } from 'react';
import { runIntegrationRecall } from '../../api/integrations';
import type { RecallResult } from '../../api/integrations';
import { jumpToL0Kernel } from '../../lib/rahoUi';
import { btnPrimaryCls, cardCls, inputCls } from './helpers';
import { ErrorBar, JsonBlock } from './shared';

export function RecallWorkbench({ enabled }: { enabled: boolean }) {
  const [query, setQuery] = useState('當前任務目標與約束');
  const [kbId, setKbId] = useState('');
  const [cubeIds, setCubeIds] = useState('default');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecallResult | null>(null);

  const run = async () => {
    if (!enabled) return;
    setBusy(true);
    setError(null);
    try {
      const out = await runIntegrationRecall({
        query,
        cube_ids: cubeIds
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        knowledge_base_id: kbId,
      });
      setResult(out);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={cardCls}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">召回試跑</h3>
          <p className="text-[11px] text-[var(--console-sub)]">MemOS ＋ OpenViking ＋ WeKnora → 注入片段（不經 LLM）</p>
        </div>
        <button type="button" className="text-[11px] text-[var(--console-accent)]" onClick={jumpToL0Kernel}>
          開啟記憶 →
        </button>
      </div>
      <ErrorBar message={error} />
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block text-[10px] text-[var(--console-sub)]">
          查詢
          <textarea className={`${inputCls} mt-1 min-h-[64px]`} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <div className="space-y-2">
          <label className="block text-[10px] text-[var(--console-sub)]">
            MemOS cube IDs（逗號分隔）
            <input className={`${inputCls} mt-1`} value={cubeIds} onChange={(e) => setCubeIds(e.target.value)} />
          </label>
          <label className="block text-[10px] text-[var(--console-sub)]">
            WeKnora knowledge_base_id
            <input className={`${inputCls} mt-1`} value={kbId} onChange={(e) => setKbId(e.target.value)} />
          </label>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button type="button" className={btnPrimaryCls} disabled={!enabled || busy || !query.trim()} onClick={() => void run()}>
          {busy ? '召回中…' : '執行召回'}
        </button>
      </div>
      {!enabled ? <p className="mt-2 text-[10px] text-[var(--console-faint)]">請先啟用至少一個召回類整合。</p> : null}
      {result ? (
        <div className="mt-3 space-y-2">
          <div className="flex flex-wrap gap-2 text-[10px] text-[var(--console-sub)]">
            <span>原因碼 {result.reason_codes?.length ?? 0}</span>
            <span>降級來源 {(result.degraded_sources ?? []).join(', ') || '無'}</span>
          </div>
          <JsonBlock value={result.token_report} />
          <JsonBlock value={result.injection || result.fragments} />
        </div>
      ) : null}
    </section>
  );
}
