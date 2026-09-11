/**
 * Apache ECharts（Apache-2.0）— 免費、無需授權金鑰。
 * 只註冊本專案用到的折線／柱狀／雷達與 Canvas 渲染。
 */
import { useEffect, useRef } from 'react';
import { BarChart, GaugeChart, LineChart, PieChart, RadarChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  RadarComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';

echarts.use([
  LineChart,
  BarChart,
  PieChart,
  GaugeChart,
  RadarChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  RadarComponent,
  CanvasRenderer,
]);

const MUTED = '#8E8E93';

export const AXIS_STYLE = {
  axisLine: { lineStyle: { color: 'rgba(255,255,255,0.16)' } },
  axisTick: { show: false },
  axisLabel: { color: MUTED, fontSize: 10 },
  splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
};

export function hexAlpha(color: string, alpha: number): string {
  const raw = color.replace('#', '');
  if (raw.length !== 6) return color;
  const n = Number.parseInt(raw, 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

export function useEChart(option: EChartsCoreOption, height: number) {
  const ref = useRef<HTMLDivElement>(null);
  const payload = JSON.stringify(option);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chart.setOption(JSON.parse(payload) as EChartsCoreOption, true);
    const resize = () => chart.resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    window.addEventListener('resize', resize);
    requestAnimationFrame(resize);
    return () => {
      window.removeEventListener('resize', resize);
      ro.disconnect();
      chart.dispose();
    };
  }, [payload, height]);

  return ref;
}
