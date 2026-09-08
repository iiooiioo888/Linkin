/**
 * 反思閉環可視化：四維雷達 + 迭代趨勢（Apache ECharts，免費）。
 */
import type { MultiDimEvaluation } from '../types';
import LcLineChart from './charts/LcLineChart';
import LcSpiderChart from './charts/LcSpiderChart';

const GREEN = '#34C759';

export function ReflectionRadar({
  multiDim,
  height = 220,
}: {
  multiDim?: MultiDimEvaluation | null;
  height?: number;
}) {
  const points = [
    { axis: '準確', value: multiDim?.accuracy?.score ?? 0 },
    { axis: '完整', value: multiDim?.completeness?.score ?? 0 },
    { axis: '清晰', value: multiDim?.clarity?.score ?? 0 },
    { axis: '相關', value: multiDim?.relevance?.score ?? 0 },
  ];
  const overall = multiDim?.overall ?? 0;

  return (
    <div className="apple-card flex h-full min-h-0 flex-col">
      <div className="apple-card__head">
        <h2 className="apple-title">四維評分</h2>
        <span className="apple-data text-[12px] text-[#007AFF]">{overall.toFixed(1)}</span>
      </div>
      <div className="apple-card__body apple-card__body--static apple-chart" style={{ height }}>
        <LcSpiderChart points={points} height={height} />
      </div>
    </div>
  );
}

export function IterationTrend({
  history,
  height = 220,
}: {
  history: Array<{ iteration: number; score: number }>;
  height?: number;
}) {
  const points =
    history.length > 0
      ? history.map((row) => ({ x: row.iteration, y: row.score }))
      : [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
        ];

  return (
    <div className="apple-card flex h-full min-h-0 flex-col">
      <div className="apple-card__head">
        <h2 className="apple-title">迭代趨勢</h2>
        <span className="text-[10px] text-[#8E8E93]">{history.length || 0} 輪</span>
      </div>
      <div className="apple-card__body apple-card__body--static apple-chart" style={{ height }}>
        <LcLineChart
          height={height}
          yMax={10}
          series={[{ id: 'score', name: '分數', color: GREEN, points }]}
        />
      </div>
    </div>
  );
}
