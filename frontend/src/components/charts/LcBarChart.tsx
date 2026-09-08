import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { AXIS_STYLE, useEChart } from '../../lib/echartsHost';

export type BarGroup = { subCategory: string; values: number[] };

const PALETTE = ['#007AFF', '#8E8E93', '#34C759', '#FF9F0A'];

export default function LcBarChart({
  categories,
  groups,
  height = 260,
}: {
  categories: string[];
  groups: BarGroup[];
  height?: number;
}) {
  const option = useMemo<EChartsCoreOption>(() => {
    const grouped = groups.length > 1;
    return {
      backgroundColor: 'transparent',
      animation: false,
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(28,28,30,0.92)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: { color: '#F5F5F7', fontSize: 11 },
      },
      legend: grouped
        ? { top: 0, textStyle: { color: '#AEAEB2', fontSize: 10 } }
        : undefined,
      grid: { left: 36, right: 8, top: grouped ? 28 : 10, bottom: 28 },
      xAxis: {
        type: 'category',
        data: categories,
        ...AXIS_STYLE,
        splitLine: { show: false },
      },
      yAxis: { type: 'value', ...AXIS_STYLE },
      series: groups.map((group, i) => ({
        name: group.subCategory,
        type: 'bar',
        barMaxWidth: 18,
        data: group.values,
        itemStyle: {
          color: group.subCategory.includes('A') ? '#8E8E93' : PALETTE[i % PALETTE.length],
          borderRadius: [4, 4, 0, 0],
        },
      })),
    };
  }, [categories, groups]);

  const host = useEChart(option, height);

  return (
    <div
      ref={host}
      className="h-full w-full"
      style={{ height, minHeight: height }}
      role="img"
      aria-label="柱狀圖"
    />
  );
}
