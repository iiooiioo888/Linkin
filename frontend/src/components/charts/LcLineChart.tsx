import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { AXIS_STYLE, hexAlpha, useEChart } from '../../lib/echartsHost';

export type LineSeriesInput = {
  id: string;
  name?: string;
  color: string;
  points: Array<{ x: number; y: number }>;
};

export default function LcLineChart({
  series,
  height = 180,
  yMax,
}: {
  series: LineSeriesInput[];
  height?: number;
  yMax?: number;
}) {
  const option = useMemo<EChartsCoreOption>(() => {
    const named = series.length > 1;
    return {
      backgroundColor: 'transparent',
      animation: false,
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(28,28,30,0.92)',
        borderColor: 'rgba(255,255,255,0.08)',
        textStyle: { color: '#F5F5F7', fontSize: 11 },
      },
      legend: named
        ? { top: 0, textStyle: { color: '#AEAEB2', fontSize: 10 }, icon: 'circle', itemWidth: 8, itemHeight: 8 }
        : undefined,
      grid: { left: 40, right: 12, top: named ? 28 : 10, bottom: 24, containLabel: false },
      xAxis: {
        type: 'value',
        min: 'dataMin',
        max: 'dataMax',
        ...AXIS_STYLE,
      },
      yAxis: {
        type: 'value',
        max: yMax,
        scale: yMax == null,
        ...AXIS_STYLE,
      },
      series: series.map((row) => ({
        id: row.id,
        name: row.name ?? row.id,
        type: 'line',
        showSymbol: row.points.length < 8,
        symbolSize: 6,
        smooth: 0.12,
        data: row.points.map((p) => [p.x, p.y]),
        lineStyle: { color: row.color, width: 2 },
        itemStyle: { color: row.color },
        areaStyle: { color: hexAlpha(row.color, 0.16) },
      })),
    };
  }, [series, yMax]);

  const host = useEChart(option, height);

  return (
    <div
      ref={host}
      className="h-full w-full"
      style={{ height, minHeight: height }}
      role="img"
      aria-label="折線圖"
    />
  );
}
