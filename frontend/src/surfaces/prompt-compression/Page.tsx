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

const field = 'reflect-field';
const primaryButton = 'reflect-action';

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
      className="reflect-page h-full overflow-y-auto [scrollbar-color:var(--console-line-strong)_transparent]"
      aria-labelledby="prompt-compression-heading"
      data-testid="prompt-compression"
    >
      <div className="reflect-spread">
        <div className="reflect-source">
          <h1 id="prompt-compression-heading" className="reflect-title">
            提示詞壓縮
          </h1>
          <p className="reflect-lead">保留頭尾並截掉中間。不經模型，也不改寫用詞。空白上限用後端預設。</p>
          <label className="reflect-label" htmlFor="prompt-truncate-text">
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
          <label className="reflect-label" htmlFor="prompt-truncate-limit">
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
          <div className="reflect-actions">
            <button type="button" className={primaryButton} onClick={() => void run()} disabled={pending}>
              {pending ? '壓縮中' : '壓縮'}
            </button>
          </div>
          {error ? (
            <p className="reflect-alert" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        <aside className="reflect-echo" aria-label="結果">
          {result ? (
            <div data-testid="prompt-truncate-result">
              <h3>壓縮結果</h3>
              <p className="reflect-note">
                原文 {result.original_chars} 字，結果 {result.result_chars} 字。
              </p>
              <p className="reflect-note">{result.helper}</p>
              <p className="whitespace-pre-wrap break-words">{result.text || '（空）'}</p>
            </div>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
