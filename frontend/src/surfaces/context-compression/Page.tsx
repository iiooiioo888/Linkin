/**
 * 上下文壓縮。三個動作各自打一條薄路由：
 * compress、extract_decisions、summarize_trace。不經模型。
 */
import { useEffect, useRef, useState } from 'react';
import {
  COMPRESS_LIMIT,
  DECISION_LIMIT,
  SUMMARY_LIMIT,
  TEXT_CAP,
  boundedLimit,
  compressContext,
  extractContextDecisions,
  summarizeContextTrace,
  type CompressContextResult,
  type SummarizeTraceResult,
} from '../../api/client/compression';
import { activeConversationText } from './sessionText';

const field = 'reflect-field';
const primaryButton = 'reflect-action';
const secondaryButton = 'reflect-action reflect-action--quiet';

type Pending = 'compress' | 'decisions' | 'summary' | null;

export function ContextCompressionPage() {
  const [text, setText] = useState('');
  const [limit, setLimit] = useState(String(COMPRESS_LIMIT.fallback));
  const [decisionLimit, setDecisionLimit] = useState(String(DECISION_LIMIT.fallback));
  const [title, setTitle] = useState('');
  const [failureReason, setFailureReason] = useState('');
  const [summaryLimit, setSummaryLimit] = useState(String(SUMMARY_LIMIT.fallback));
  const [compressed, setCompressed] = useState<CompressContextResult | null>(null);
  const [decisions, setDecisions] = useState<string[] | null>(null);
  const [decisionHelper, setDecisionHelper] = useState('');
  const [summary, setSummary] = useState<SummarizeTraceResult | null>(null);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState<Pending>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!error && !notice) return;
    feedbackRef.current?.scrollIntoView({ block: 'nearest' });
  }, [error, notice]);

  function fillFromSession() {
    const next = activeConversationText();
    if (!next) {
      setNotice('');
      setError('這段對話還沒有內容。');
      return;
    }
    setText(next);
    setError('');
    setNotice('已帶入本機對話。');
  }

  async function runCompress() {
    if (!text.trim()) {
      setError('請先貼上要壓縮的上下文。');
      setNotice('');
      return;
    }
    if (text.length > TEXT_CAP) {
      setError(`文字超過 ${TEXT_CAP} 字。`);
      setNotice('');
      return;
    }
    const parsed = boundedLimit(limit, COMPRESS_LIMIT);
    if (!parsed.ok) {
      setError(parsed.message);
      setNotice('');
      return;
    }
    setPending('compress');
    setError('');
    setNotice('');
    try {
      setCompressed(await compressContext(text, parsed.value));
    } catch (err) {
      setError(err instanceof Error ? err.message : '壓縮沒有完成。');
    } finally {
      setPending(null);
    }
  }

  async function runDecisions() {
    if (!text.trim()) {
      setError('請先貼上要抽出決策的上下文。');
      setNotice('');
      return;
    }
    const parsed = boundedLimit(decisionLimit, DECISION_LIMIT);
    if (!parsed.ok) {
      setError(parsed.message);
      setNotice('');
      return;
    }
    setPending('decisions');
    setError('');
    setNotice('');
    try {
      const result = await extractContextDecisions(text, parsed.value);
      setDecisions(result.decisions);
      setDecisionHelper(result.helper);
    } catch (err) {
      setError(err instanceof Error ? err.message : '抽出決策沒有完成。');
    } finally {
      setPending(null);
    }
  }

  async function runSummary() {
    if (!title.trim() && !text.trim() && !failureReason.trim()) {
      setError('標題、正文、失敗原因至少填一項。');
      setNotice('');
      return;
    }
    const parsed = boundedLimit(summaryLimit, SUMMARY_LIMIT);
    if (!parsed.ok) {
      setError(parsed.message);
      setNotice('');
      return;
    }
    setPending('summary');
    setError('');
    setNotice('');
    try {
      setSummary(
        await summarizeContextTrace({
          title,
          body: text,
          failureReason,
          limit: parsed.value,
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '摘要沒有完成。');
    } finally {
      setPending(null);
    }
  }

  const busy = pending !== null;

  return (
    <section
      className="reflect-page h-full overflow-y-auto [scrollbar-color:var(--console-line-strong)_transparent]"
      aria-labelledby="context-compression-heading"
      data-testid="context-compression"
    >
      <div className="reflect-spread">
        <div className="reflect-source">
          <h1 id="context-compression-heading" className="reflect-title">
            上下文壓縮
          </h1>
          <p className="reflect-lead">
            規則截斷與關鍵句抽取，不經模型。空白上限會用各函式的預設值。
          </p>
          <div ref={feedbackRef}>
            {notice ? (
              <p className="reflect-note" role="status">
                {notice}
              </p>
            ) : null}
            {error ? (
              <p className="reflect-alert" role="alert">
                {error}
              </p>
            ) : null}
          </div>

          <label className="reflect-label" htmlFor="context-compress-text">
            上下文
            <textarea
              id="context-compress-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={8}
              className={`${field} min-h-32 resize-y`}
              data-testid="context-compress-text"
            />
          </label>
          <div className="reflect-actions">
            <button type="button" className={secondaryButton} onClick={fillFromSession} disabled={busy}>
              帶入本機對話
            </button>
          </div>

          <label className="reflect-label" htmlFor="context-compress-limit">
            壓縮上限（字）
            <input
              id="context-compress-limit"
              inputMode="numeric"
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
              className={field}
            />
          </label>
          <div className="reflect-actions">
            <button type="button" className={primaryButton} onClick={() => void runCompress()} disabled={busy}>
              {pending === 'compress' ? '壓縮中' : '壓縮'}
            </button>
          </div>

          <div className="reflect-block">
            <h2>決策</h2>
            <label className="reflect-label" htmlFor="context-decision-limit">
              最多幾句
              <input
                id="context-decision-limit"
                inputMode="numeric"
                value={decisionLimit}
                onChange={(event) => setDecisionLimit(event.target.value)}
                className={field}
              />
            </label>
            <div className="reflect-actions">
              <button type="button" className={primaryButton} onClick={() => void runDecisions()} disabled={busy}>
                {pending === 'decisions' ? '抽出中' : '抽出決策'}
              </button>
            </div>
          </div>

          <div className="reflect-block">
            <h2>軌跡摘要</h2>
            <p className="reflect-note">正文沿用上方的上下文。</p>
            <label className="reflect-label" htmlFor="context-summary-title">
              標題
              <input
                id="context-summary-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className={field}
              />
            </label>
            <label className="reflect-label" htmlFor="context-summary-failure">
              失敗原因
              <input
                id="context-summary-failure"
                value={failureReason}
                onChange={(event) => setFailureReason(event.target.value)}
                className={field}
              />
            </label>
            <label className="reflect-label" htmlFor="context-summary-limit">
              摘要上限（字）
              <input
                id="context-summary-limit"
                inputMode="numeric"
                value={summaryLimit}
                onChange={(event) => setSummaryLimit(event.target.value)}
                className={field}
              />
            </label>
            <div className="reflect-actions">
              <button type="button" className={primaryButton} onClick={() => void runSummary()} disabled={busy}>
                {pending === 'summary' ? '摘要中' : '做成摘要'}
              </button>
            </div>
          </div>
        </div>
        <aside className="reflect-echo" aria-label="結果">
          {compressed ? (
            <Result
              title="壓縮結果"
              helper={compressed.helper}
              meta={`原文 ${compressed.original_chars} 字，結果 ${compressed.result_chars} 字。`}
              body={compressed.text || '（空）'}
              testId="context-compress-result"
            />
          ) : null}
          {decisions ? (
            <div data-testid="context-decisions-result">
              <h3>決策</h3>
              <p className="reflect-note">{decisionHelper}</p>
              {decisions.length === 0 ? (
                <p className="reflect-note">沒有抽出決策句。</p>
              ) : (
                <ul>
                  {decisions.map((item, index) => (
                    <li key={`${index}-${item}`} className="whitespace-pre-wrap break-words">
                      {item}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
          {summary ? (
            <Result
              title="摘要"
              helper={summary.helper}
              body={summary.summary || '（空）'}
              testId="context-summary-result"
            />
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function Result({
  title,
  helper,
  meta,
  body,
  testId,
}: {
  title: string;
  helper: string;
  meta?: string;
  body: string;
  testId: string;
}) {
  return (
    <div data-testid={testId}>
      <h3>{title}</h3>
      {meta ? <p className="reflect-note">{meta}</p> : null}
      <p className="reflect-note">{helper}</p>
      <p className="whitespace-pre-wrap break-words">{body}</p>
    </div>
  );
}
