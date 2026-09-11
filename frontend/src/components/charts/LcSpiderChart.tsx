import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { hexAlpha, useEChart } from '../../lib/echartsHost';

export type SpiderPoint = { axis: string; value: number };

export default function LcSpiderChart({
  points,
  height = 220,
  max = 10,
}: {
  points: SpiderPoint[];
  height?: number;
  max?: number;
}) {
  const option = useMemo<EChartsCoreOption>(
    () => ({
      backgroundColor: 'transparent',
      animation: false,
      radar: {
        indicator: points.map((p) => ({ name: p.axis, max })),
        splitNumber: 4,
        axisName: { color: '#AEAEB2', fontSize: 11 },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
        splitArea: { areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.04)'] } },
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.12)' } },
      },
      series: [
        {
          type: 'radar',
          symbol: 'circle',
          symbolSize: 6,
          data: [
            {
              value: points.map((p) => p.value),
              name: 'score',
              lineStyle: { color: 'var(--console-blue)', width: 2 },
              itemStyle: { color: 'var(--console-blue)' },
              areaStyle: { color: hexAlpha('var(--console-blue)', 0.28) },
            },
          ],
        },
      ],
    }),
    [points, max],
  );

  const host = useEChart(option, height);

  return (
    <div
      ref={host}
      className="mx-auto h-full w-full"
      style={{ height, minHeight: height }}
      role="img"
      aria-label="雷達圖"
    />
  );
}
