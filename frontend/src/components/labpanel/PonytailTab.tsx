/**
 * Ponytail 分頁：精簡審查輸入、審查結果（可刪除／必保留／改寫建議）。
 */
import type { Dispatch, SetStateAction } from 'react';
import type { PonytailReviewResult } from '../../api/client';
import ErrorState from '../ui/ErrorState';
import PromptEditor from '../PromptEditor';
import { tabBtn } from './constants';

export function PonytailTab({
  reviewInput,
  setReviewInput,
  reviewKind,
  setReviewKind,
  reviewResult,
  reviewLoading,
  reviewError,
  runPonytailReview,
}: {
  reviewInput: string;
  setReviewInput: Dispatch<SetStateAction<string>>;
  reviewKind: 'code' | 'prompt' | 'diff';
  setReviewKind: Dispatch<SetStateAction<'code' | 'prompt' | 'diff'>>;
  reviewResult: PonytailReviewResult | null;
  reviewLoading: boolean;
  reviewError: string | null;
  runPonytailReview: () => Promise<void>;
}) {
  return (
          <div className="mx-auto max-w-3xl space-y-4">
            <p className="text-[11px] text-[var(--console-sub)]">
              懶惰資深工程師模式 — 審查過度工程化，停在第一個夠用的梯級。
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {(['code', 'prompt', 'diff'] as const).map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setReviewKind(k)}
                  className={tabBtn(reviewKind === k)}
                >
                  {k}
                </button>
              ))}
              <button
                type="button"
                disabled={reviewLoading}
                onClick={() => void runPonytailReview()}
                className="ml-auto rounded-full bg-[var(--console-green)] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
              >
                {reviewLoading ? '審查中…' : 'Ponytail 審查'}
              </button>
            </div>
            <PromptEditor value={reviewInput} onChange={setReviewInput} height={200} language="typescript" />
            {reviewResult && (
              <section className="apple-card apple-card--pad space-y-3">
                <p className="text-[13px] font-bold text-[var(--console-ink)]">{reviewResult.review.summary}</p>
                {reviewResult.review.delete_list && reviewResult.review.delete_list.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold text-[var(--console-danger)]">可刪除</p>
                    <ul className="mt-1 list-inside list-disc text-[12px] text-[var(--console-sub)]">
                      {reviewResult.review.delete_list.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {reviewResult.review.keep_list && reviewResult.review.keep_list.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold text-[var(--console-green)]">必須保留</p>
                    <ul className="mt-1 list-inside list-disc text-[12px] text-[var(--console-sub)]">
                      {reviewResult.review.keep_list.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {reviewResult.review.suggested_rewrite && (
                  <pre className="overflow-x-auto rounded-lg bg-black/30 p-3 text-[11px] text-[var(--console-ink)]">
                    {reviewResult.review.suggested_rewrite}
                  </pre>
                )}
              </section>
            )}
            {reviewError && <ErrorState kind="generic" compact message={reviewError} />}
          </div>
  );
}
