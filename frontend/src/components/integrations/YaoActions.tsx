/**
 * 整合面板 Yao 任務板動作區。
 */
import { useState } from 'react';
import { yaoCreateTask, yaoListTasks, yaoListWorkspaces } from '../../api/integrations';
import { btnCls, btnPrimaryCls, inputCls } from './helpers';
import { ErrorBar, JsonBlock, OkBar } from './shared';

export function YaoActions() {
  const [workspaceId, setWorkspaceId] = useState('');
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
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
        const code =
          typeof out === 'object' && out && 'error_code' in out
            ? String((out as { error_code?: string }).error_code || 'ERR')
            : 'ERR';
        setError(code);
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
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnCls} disabled={busy} onClick={() => void run(() => yaoListWorkspaces(), '已列出工作區')}>
          列出工作區
        </button>
        <button
          type="button"
          className={btnCls}
          disabled={busy || !workspaceId.trim()}
          onClick={() => void run(() => yaoListTasks(workspaceId.trim()), '已列出任務')}
        >
          列出任務
        </button>
      </div>
      <label className="block text-[10px] text-[var(--console-sub)]">
        workspace_id
        <input className={`${inputCls} mt-1`} value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)} />
      </label>
      <label className="block text-[10px] text-[var(--console-sub)]">
        任務標題
        <input className={`${inputCls} mt-1`} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="block text-[10px] text-[var(--console-sub)]">
        任務 prompt
        <textarea className={`${inputCls} mt-1 min-h-[56px]`} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </label>
      <button
        type="button"
        className={btnPrimaryCls}
        disabled={busy || !workspaceId.trim() || !title.trim() || !prompt.trim()}
        onClick={() =>
          void run(
            () =>
              yaoCreateTask({
                workspace_id: workspaceId.trim(),
                title: title.trim(),
                prompt: prompt.trim(),
              }),
            '任務已建立（顯式）',
          )
        }
      >
        建立任務
      </button>
      <JsonBlock value={payload} />
    </div>
  );
}
