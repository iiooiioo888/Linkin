import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useEChart } from '../../lib/echartsHost';

export type PieSlice = { name: string; value: number };

const PALETTE = ['#007AFF', '#34C759', '#FF9F0A', '#FF2D55', '#5856D6', '#8E8E93'];

export default function LcPieChart({
  slices,
  height = 240,
}: {
  slices: PieSlice[];
  height?: number;
}) {
  const option = useMemo<EChartsCoreOption>(
    () => ({
      backgroundColor: 'transparent',
      animation: false,
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(28,28,30,0.92)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: { color: '#F5F5F7', fontSize: 11 },
      },
      legend: {
        bottom: 0,
        textStyle: { color: '#AEAEB2', fontSize: 10 },
      },
      series: [
        {
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['50%', '46%'],
          data: slices.map((slice, i) => ({
            name: slice.name,
            value: slice.value,
            itemStyle: { color: PALETTE[i % PALETTE.length] },
          })),
          label: { color: '#AEAEB2', fontSize: 10 },
        },
      ],
    }),
    [slices],
  );

  const host = useEChart(option, height);

  return (
    <div
      ref={host}
      className="h-full w-full"
      style={{ height, minHeight: height }}
      role="img"
      aria-label="餅圖"
    />
  );
}
