/**
 * Archify 分頁：系統流程圖、自訂描述生成的架構 IR 與錯誤提示。
 */
import { useMemo, type Dispatch, type SetStateAction } from 'react';
import type { ArchifyIR, SystemFlowEntry } from '../../api/client';
import ArchifyFrame from '../ArchifyFrame';
import ErrorState from '../ui/ErrorState';

export function ArchifyTab({
  archFlows,
  archFlowView,
  setArchFlowView,
  archCustomIr,
  setArchCustomIr,
  archDesc,
  setArchDesc,
  archLoading,
  archCatalogLoading,
  archError,
  runArchifyGenerate,
}: {
  archFlows: SystemFlowEntry[];
  archFlowView: string;
  setArchFlowView: Dispatch<SetStateAction<string>>;
  archCustomIr: ArchifyIR | null;
  setArchCustomIr: Dispatch<SetStateAction<ArchifyIR | null>>;
  archDesc: string;
  setArchDesc: Dispatch<SetStateAction<string>>;
  archLoading: boolean;
  archCatalogLoading: boolean;
  archError: string | null;
  runArchifyGenerate: () => Promise<void>;
}) {
  const activeArchFlow = useMemo(
    () => archFlows.find((row) => row.id === archFlowView) ?? null,
    [archFlows, archFlowView],
  );

  return (
          <div className="mx-auto max-w-4xl space-y-4">
            <section className="apple-card apple-card--pad space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="apple-title">系統流程圖</p>
                {archCatalogLoading && (
                  <span className="text-[10px] text-[var(--console-sub)]">載入目錄…</span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {archFlows.map((flow) => (
                  <button
                    key={flow.id}
                    type="button"
                    onClick={() => {
                      setArchFlowView(flow.id);
                      setArchCustomIr(null);
                    }}
                    className={`rounded-full border px-3 py-1.5 text-[11px] font-bold transition-colors ${
                      archFlowView === flow.id && !archCustomIr
                        ? 'border-[color-mix(in_srgb,var(--console-accent)_60%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_15%,transparent)] text-[var(--console-ink)]'
                        : 'border-white/10 text-[var(--console-sub)] hover:border-white/20 hover:text-[var(--console-ink)]'
                    }`}
                  >
                    {flow.title}
                  </button>
                ))}
              </div>
              {activeArchFlow && !archCustomIr ? (
                <div className="rounded-xl border border-white/[0.06] bg-black/20 px-3 py-2">
                  <p className="text-[12px] font-semibold text-[var(--console-ink)]">{activeArchFlow.title}</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-[var(--console-sub)]">{activeArchFlow.blurb}</p>
                  <p className="mt-1 text-[10px] text-[var(--console-sub)]">
                    view={activeArchFlow.id} · {activeArchFlow.diagram_type}
                  </p>
                </div>
              ) : null}
            </section>
            {!archCustomIr && archFlowView ? (
              <ArchifyFrame key={archFlowView} view={archFlowView} />
            ) : null}
            <section className="apple-card apple-card--pad space-y-2">
              <p className="apple-title">自訂描述 → 架構 IR</p>
              <textarea
                value={archDesc}
                onChange={(e) => setArchDesc(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-white/[0.08] bg-[var(--console-card)] px-3 py-2 text-[12px] text-[var(--console-ink)]"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={archLoading}
                  onClick={() => void runArchifyGenerate()}
                  className="rounded-full bg-[var(--console-purple)] px-4 py-1.5 text-[12px] font-bold text-white disabled:opacity-50"
                >
                  {archLoading ? '生成中…' : '生成架構圖'}
                </button>
                {archCustomIr ? (
                  <button
                    type="button"
                    onClick={() => setArchCustomIr(null)}
                    className="rounded-full border border-white/10 px-3 py-1.5 text-[11px] font-bold text-[var(--console-sub)] hover:text-[var(--console-ink)]"
                  >
                    回到系統流程
                  </button>
                ) : null}
              </div>
            </section>
            {archCustomIr ? <ArchifyFrame ir={archCustomIr} fallbackIr={archCustomIr} /> : null}
            {archError && <ErrorState kind="generic" compact message={archError} />}
          </div>
  );
}
