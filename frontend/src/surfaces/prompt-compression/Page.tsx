/**
 * 提示詞壓縮。沒有壓縮 API 時只標缺口，不呼叫優化或其他 LLM 管線。
 */
import { PROMPT_COMPRESSION_GAP } from './gap.ts';

export function Page() {
  const gap = PROMPT_COMPRESSION_GAP;
  return (
    <main className="evo-content console-canvas px-[var(--u3)] py-[var(--u4)]" data-testid="prompt-compression">
      <h1 className="apple-heading">提示詞壓縮</h1>
      <p className="mt-[var(--u2)] max-w-[68ch] text-[13px] leading-relaxed text-[var(--console-sub)]">
        <span className="text-[var(--console-amber)]">{gap.status}</span>
        。缺少{gap.missing}。{gap.detail}
      </p>
      <dl className="mt-[var(--u3)] max-w-[68ch] space-y-[var(--u3)]">
        <div>
          <dt className="text-[13px] font-semibold text-[var(--console-ink)]">不能挪用</dt>
          <dd className="mt-[var(--u)] text-[13px] leading-relaxed text-[var(--console-sub)]">
            <code className="apple-data text-[12px] text-[var(--console-ink)]">
              {gap.notThis.method} {gap.notThis.path}
            </code>
            。{gap.notThis.why}
          </dd>
        </div>
        <div>
          <dt className="text-[13px] font-semibold text-[var(--console-ink)]">沒有對外路由</dt>
          <dd className="mt-[var(--u)] text-[13px] leading-relaxed text-[var(--console-sub)]">
            <ul className="space-y-1">
              {gap.internalOnly.map((name) => (
                <li key={name}>
                  <code className="apple-data text-[12px] text-[var(--console-ink)]">{name}</code>
                </li>
              ))}
            </ul>
          </dd>
        </div>
      </dl>
    </main>
  );
}
