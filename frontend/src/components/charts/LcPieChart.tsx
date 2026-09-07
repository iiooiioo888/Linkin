import { useEffect, useMemo, useRef, useState } from 'react';
import { darkTheme, getLcFactory } from '../../lib/lcjsHost';
import LcBarChart from './LcBarChart';

export type PieSlice = { name: string; value: number };

function FallbackPie({ slices, height }: { slices: PieSlice[]; height: number }) {
  const total = Math.max(1, slices.reduce((sum, s) => sum + s.value, 0));
  return (
    <LcBarChart
      height={height}
      categories={slices.map((s) => s.name)}
      groups={[{ subCategory: '佔比', values: slices.map((s) => Math.round((s.value / total) * 1000) / 10) }]}
    />
  );
}

export default function LcPieChart({
  slices,
  height = 240,
}: {
  slices: PieSlice[];
  height?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<'lcjs' | 'fallback'>('lcjs');
  const payload = useMemo(() => JSON.stringify(slices), [slices]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let chart: { dispose: () => void } | null = null;

    void (async () => {
      const [lc, theme] = await Promise.all([getLcFactory(), darkTheme()]);
      if (disposed) return;
      const pieFn = lc && 'Pie' in lc ? (lc as { Pie?: (opts: unknown) => Record<string, unknown> }).Pie : undefined;
      if (!lc || !theme || !pieFn) {
        setMode('fallback');
        return;
      }
      try {
        setMode('lcjs');
        const pie = pieFn({ container: el, theme, animationsEnabled: false }) as {
          setTitle?: (v: string) => unknown;
          setInnerRadius?: (v: number) => unknown;
          addSlice?: (name: string, value: number) => unknown;
          setData?: (rows: Array<{ name: string; value: number }>) => unknown;
          dispose: () => void;
        };
        pie.setTitle?.('');
        pie.setInnerRadius?.(40);
        if (typeof pie.setData === 'function') {
          pie.setData(slices);
        } else {
          for (const slice of slices) pie.addSlice?.(slice.name, slice.value);
        }
        chart = pie;
      } catch (err) {
        console.warn('[lcjs] Pie 初始化失敗', err);
        setMode('fallback');
      }
    })();

    return () => {
      disposed = true;
      chart?.dispose();
    };
  }, [payload, slices]);

  if (mode === 'fallback') {
    return <FallbackPie slices={slices} height={height} />;
  }
  return <div ref={host} className="h-full w-full" style={{ minHeight: height }} />;
}
