/**
 * 提示詞壓縮。只呼叫 templates.truncate 的薄路由，不改寫用詞，也不走優化。
 */
import { useState } from 'react';
import {
  TEXT_CAP,
  TRUNCATE_LIMIT,
  boundedLimit,
  truncatePrompt,
  type TruncatePromptResult,
} from '../../api/client/compression.ts';

const focusRing =
  'focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:[outline-color:var(--console-accent)]!';

const field =
  'mt-1 w-full rounded-[10px] border border-[var(--console-line)] bg-[var(--console-card)] px-3 py-2 text-[13px] leading-normal text-[var(--console-ink)]';

const primaryButton = `self-start inline-flex min-h-11 items-center rounded-[10px] bg-[var(--console-accent)] px-3.5 text-[12px] font-medium text-[var(--console-accent-ink)] disabled:opacity-50 ${focusRing}`;

export function Page() {
  const [text, setText] = useState('');
  const [limit, setLimit] = useState('');
  const [result, setResult] = useState<TruncatePromptResult | null>(null);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  async function run() {
    if (!text.trim()) {
      setError('請先貼上提示詞。');
      return;
    }
    if (text.length > TEXT_CAP) {
      setError(`文字超過 ${TEXT_CAP} 字。`);
      return;
    }
    const parsed = boundedLimit(limit, TRUNCATE_LIMIT);
    if (!parsed.ok) {
      setError(parsed.message);
      return;
    }
    setPending(true);
    setError('');
    try {
      setResult(await truncatePrompt(text, parsed.value));
    } catch (err) {
      setError(err instanceof Error ? err.message : '壓縮沒有完成。');
    } finally {
      setPending(false);
    }
  }

  return (
    <section
      className="h-full overflow-y-auto bg-[var(--console-bg)] text-[var(--console-ink)] [scrollbar-color:var(--console-line-strong)_transparent]"
      aria-labelledby="prompt-compression-heading"
      data-testid="prompt-compression"
    >
      <div className="mx-auto flex w-full max-w-[72ch] flex-col px-[var(--u3)] py-[var(--u4)] sm:px-[var(--u4)]">
        <h1 id="prompt-compression-heading" className="text-[22px] font-semibold leading-[1.25] tracking-[-0.02em]">
          提示詞壓縮
        </h1>
        <p className="mt-2 text-[13px] leading-normal text-[var(--console-sub)]">
          保留頭尾並截掉中間。不經模型，也不改寫用詞。空白上限用後端預設。
        </p>
        <label className="mt-[var(--u4)] text-[12px] text-[var(--console-sub)]" htmlFor="prompt-truncate-text">
          提示詞
          <textarea
            id="prompt-truncate-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={8}
            className={`${field} min-h-32 resize-y`}
            data-testid="prompt-truncate-text"
          />
        </label>
        <label className="mt-[var(--u3)] text-[12px] text-[var(--console-sub)]" htmlFor="prompt-truncate-limit">
          上限（字）
          <input
            id="prompt-truncate-limit"
            inputMode="numeric"
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
            placeholder="預設"
            className={field}
          />
        </label>
        <button type="button" className={`mt-[var(--u3)] ${primaryButton}`} onClick={() => void run()} disabled={pending}>
          {pending ? '壓縮中' : '壓縮'}
        </button>
        {result ? (
          <div className="mt-[var(--u4)]" data-testid="prompt-truncate-result">
            <p className="text-[12px] text-[var(--console-sub)]">
              原文 {result.original_chars} 字，結果 {result.result_chars} 字。
            </p>
            <p className="mt-1 text-[12px] text-[var(--console-sub)]">{result.helper}</p>
            <p className="mt-2 whitespace-pre-wrap break-words text-[13px] leading-normal">
              {result.text || '（空）'}
            </p>
          </div>
        ) : null}
        {error ? (
          <p className="mt-[var(--u3)] text-[13px] leading-normal text-[var(--console-amber)]" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}
