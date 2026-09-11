import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useEChart } from '../../lib/echartsHost';
import { CHART_PALETTE } from '../../lib/consoleColors';

export type PieSlice = { name: string; value: number; color?: string };

const DEFAULT_COLORS = [...CHART_PALETTE];

export default function LcPieChart({
  slices,
  height = 220,
  emptyLabel = '暫無資料',
}: {
  slices: PieSlice[];
  height?: number;
  emptyLabel?: string;
}) {
  const hasData = slices.some((s) => s.value > 0);
  const option = useMemo<EChartsCoreOption>(() => {
    const data = hasData
      ? slices.filter((s) => s.value > 0).map((s, i) => ({
          name: s.name,
          value: s.value,
          itemStyle: { color: s.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length] },
        }))
      : [{ name: emptyLabel, value: 1, itemStyle: { color: 'rgba(255,255,255,0.08)' } }];
    return {
      backgroundColor: 'transparent',
      animation: false,
      tooltip: {
        trigger: 'item',
        backgroundColor: 'rgba(28,28,30,0.92)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: { color: 'var(--console-ink)', fontSize: 11 },
        formatter: hasData ? undefined : () => emptyLabel,
      },
      legend: {
        bottom: 0,
        textStyle: { color: 'var(--console-sub)', fontSize: 10 },
        icon: 'circle',
        itemWidth: 8,
        itemHeight: 8,
      },
      series: [
        {
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          label: { show: hasData, color: 'var(--console-sub)', fontSize: 10, formatter: '{b}\n{d}%' },
          labelLine: { lineStyle: { color: 'rgba(255,255,255,0.2)' } },
          data,
        },
      ],
    };
  }, [slices, hasData, emptyLabel]);

  const host = useEChart(option, height);
  return (
    <div ref={host} className="h-full w-full" style={{ height, minHeight: height }} role="img" aria-label="圓餅圖" />
  );
}
