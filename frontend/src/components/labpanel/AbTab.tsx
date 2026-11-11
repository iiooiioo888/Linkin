/**
 * A/B 分頁：記憶蒸餾評分對照長條圖與勝出變體摘要。
 */
import { useMemo } from 'react';
import LcBarChart from '../charts/LcBarChart';
import { AB_SERIES } from './constants';

export function AbTab() {
  const winner = useMemo(() => {
    const scoreA = AB_SERIES.reduce((s, r) => s + r.a, 0) / AB_SERIES.length;
    const scoreB = AB_SERIES.reduce((s, r) => s + r.b, 0) / AB_SERIES.length;
    return { scoreA, scoreB, better: scoreB >= scoreA ? 'B' : 'A' };
  }, []);

  return (
          <div className="grid gap-5 lg:grid-cols-[1fr_220px]">
            <section className="apple-card">
              <div className="apple-card__head">
                <h2 className="apple-title">記憶蒸餾 · 評分對照</h2>
              </div>
              <div className="apple-card__body apple-card__body--static apple-chart h-[280px]">
                <LcBarChart
                  height={280}
                  categories={AB_SERIES.map((row) => row.name)}
                  groups={[
                    { subCategory: '對照組 A', values: AB_SERIES.map((row) => row.a) },
                    { subCategory: '實驗組 B', values: AB_SERIES.map((row) => row.b) },
                  ]}
                />
              </div>
            </section>
            <section className="apple-card apple-card--pad flex flex-col justify-center gap-4">
              <div>
                <p className="apple-title">勝出</p>
                <p className="mt-2 text-[28px] font-bold text-[var(--console-accent)]">變體 {winner.better}</p>
              </div>
              <div>
                <p className="text-[11px] text-[var(--console-sub)]">A 均分</p>
                <p className="apple-data text-[18px]">{winner.scoreA.toFixed(2)}</p>
              </div>
              <div>
                <p className="text-[11px] text-[var(--console-sub)]">B 均分</p>
                <p className="apple-data text-[18px] text-[var(--console-green)]">{winner.scoreB.toFixed(2)}</p>
              </div>
            </section>
          </div>
  );
}
