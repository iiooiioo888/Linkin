/**
 * 整合面板 OpenPencil 專案列表與設計生成動作區。
 */
import { useState } from 'react';
import { openpencilGenerate, openpencilListProjects } from '../../api/integrations';
import { btnCls, btnPrimaryCls, inputCls } from './helpers';
import { ErrorBar, JsonBlock, OkBar } from './shared';

export function OpenPencilActions() {
  const [prompt, setPrompt] = useState('');
  const [style, setStyle] = useState('');
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
      const ok = typeof out === 'object' && out && 'ok' in out ? Boolean((out as { ok: boolean }).ok) : true;
      if (!ok) {
        setError(String((out as { error_code?: string }).error_code || '失敗'));
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
      <button type="button" className={btnCls} disabled={busy} onClick={() => void run(() => openpencilListProjects(), '已列出專案')}>
        列出專案
      </button>
      <label className="block text-[10px] text-[var(--console-sub)]">
        設計 prompt
        <textarea className={`${inputCls} mt-1 min-h-[56px]`} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </label>
      <label className="block text-[10px] text-[var(--console-sub)]">
        style（可選）
        <input className={`${inputCls} mt-1`} value={style} onChange={(e) => setStyle(e.target.value)} />
      </label>
      <button
        type="button"
        className={btnPrimaryCls}
        disabled={busy || !prompt.trim()}
        onClick={() =>
          void run(
            () => openpencilGenerate({ prompt: prompt.trim(), style: style.trim() || undefined }),
            '設計生成已觸發（顯式）',
          )
        }
      >
        生成設計
      </button>
      <JsonBlock value={payload} />
    </div>
  );
}
