/**
 * 提示詞優化分頁：模式／目標輸入、優化前後對照與錯誤提示。
 */
import type { Dispatch, SetStateAction } from 'react';
import ErrorState from '../ui/ErrorState';
import PromptEditor from '../PromptEditor';

export function PromptTab({
  before,
  setBefore,
  after,
  setAfter,
  promptMode,
  setPromptMode,
  promptGoal,
  setPromptGoal,
  promptLoading,
  promptError,
  runPromptOptimize,
}: {
  before: string;
  setBefore: Dispatch<SetStateAction<string>>;
  after: string;
  setAfter: Dispatch<SetStateAction<string>>;
  promptMode: 'user' | 'system';
  setPromptMode: Dispatch<SetStateAction<'user' | 'system'>>;
  promptGoal: string;
  setPromptGoal: Dispatch<SetStateAction<string>>;
  promptLoading: boolean;
  promptError: string | null;
  runPromptOptimize: () => Promise<void>;
}) {
  return (
          <div className="mx-auto max-w-5xl space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={promptMode}
                onChange={(e) => setPromptMode(e.target.value as 'user' | 'system')}
                className="rounded-lg border border-white/[0.08] bg-[var(--console-card)] px-2 py-1 text-[11px] text-[var(--console-ink)]"
              >
                <option value="user">User 提示詞</option>
                <option value="system">System 提示詞</option>
              </select>
              <input
                value={promptGoal}
                onChange={(e) => setPromptGoal(e.target.value)}
                placeholder="優化目標"
                className="min-w-[180px] flex-1 rounded-lg border border-white/[0.08] bg-[var(--console-card)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
              />
              <button
                type="button"
                disabled={promptLoading}
                onClick={() => void runPromptOptimize()}
                className="rounded-full bg-[var(--console-accent)] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
              >
                {promptLoading ? '優化中…' : '一鍵優化'}
              </button>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <section className="apple-card">
                <div className="apple-card__head">
                  <h2 className="apple-title">優化前</h2>
                </div>
                <div className="apple-card__body apple-card__body--static !pt-0">
                  <PromptEditor value={before} onChange={setBefore} height={240} />
                </div>
              </section>
              <section className="apple-card">
                <div className="apple-card__head">
                  <h2 className="apple-title">優化後</h2>
                  <span className="text-[10px] font-bold text-[var(--console-green)]">LLM</span>
                </div>
                <div className="apple-card__body apple-card__body--static !pt-0">
                  <PromptEditor
                    value={after || '（點「一鍵優化」產生結果）'}
                    onChange={setAfter}
                    height={240}
                    readOnly={!after}
                  />
                </div>
              </section>
            </div>
            {promptError && <ErrorState kind="generic" compact message={promptError} />}
          </div>
  );
}
