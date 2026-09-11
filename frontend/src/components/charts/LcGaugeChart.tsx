import { useMemo } from 'react';
import type { EChartsCoreOption } from 'echarts/core';
import { useEChart } from '../../lib/echartsHost';

export default function LcGaugeChart({
  value,
  max,
  label,
  sublabel,
  height = 180,
}: {
  value: number;
  max: number;
  label: string;
  sublabel?: string;
  height?: number;
}) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const option = useMemo<EChartsCoreOption>(
    () => ({
      backgroundColor: 'transparent',
      animation: false,
      series: [
        {
          type: 'gauge',
          startAngle: 200,
          endAngle: -20,
          min: 0,
          max: 100,
          radius: '88%',
          center: ['50%', '58%'],
          progress: {
            show: true,
            width: 10,
            itemStyle: { color: '#64D2FF' },
          },
          axisLine: { lineStyle: { width: 10, color: [[1, 'rgba(255,255,255,0.08)']] } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          pointer: { show: false },
          anchor: { show: false },
          detail: {
            valueAnimation: false,
            offsetCenter: [0, '8%'],
            formatter: () => `${value.toFixed(1)}\n/ ${max.toFixed(1)}`,
            color: '#F5F5F7',
            fontSize: 14,
            lineHeight: 18,
          },
          title: {
            offsetCenter: [0, '72%'],
            color: '#8E8E93',
            fontSize: 10,
          },
          data: [{ value: pct, name: label }],
        },
      ],
    }),
    [value, max, pct, label],
  );

  const host = useEChart(option, height);
  return (
    <div className="relative h-full w-full" style={{ height, minHeight: height }}>
      <div ref={host} className="h-full w-full" role="img" aria-label="儀表圖" />
      {sublabel ? (
        <p className="pointer-events-none absolute bottom-1 left-0 right-0 text-center text-[10px] text-[#636366]">
          {sublabel}
        </p>
      ) : null}
    </div>
  );
}
