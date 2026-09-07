import { useEffect, useMemo, useRef, useState } from 'react';
import { darkTheme, getLcFactory, loadLcjs } from '../../lib/lcjsHost';

export type LineSeriesInput = {
  id: string;
  name?: string;
  color: string;
  points: Array<{ x: number; y: number }>;
};

function FallbackLine({ series, height }: { series: LineSeriesInput[]; height: number }) {
  const w = 640;
  const h = Math.max(80, height);
  const allY = series.flatMap((s) => s.points.map((p) => p.y));
  const allX = series.flatMap((s) => s.points.map((p) => p.x));
  const minY = allY.length ? Math.min(...allY) : 0;
  const maxY = allY.length ? Math.max(...allY) : 1;
  const spanY = maxY - minY || Math.abs(maxY) || 1;
  const minX = allX.length ? Math.min(...allX) : 0;
  const maxX = allX.length ? Math.max(...allX) : minX + 1;
  const spanX = maxX - minX || 1;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="h-full w-full" role="img" aria-label="折線圖">
      {series.map((s) => {
        const d = s.points
          .map((p, i) => {
            const x = 8 + ((p.x - minX) / spanX) * (w - 16);
            const y = h - 10 - ((p.y - minY) / spanY) * (h - 20);
            return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
          })
          .join(' ');
        return <path key={s.id} d={d} fill="none" stroke={s.color} strokeWidth="2" />;
      })}
    </svg>
  );
}

export default function LcLineChart({
  series,
  height = 180,
  yMax,
}: {
  series: LineSeriesInput[];
  height?: number;
  yMax?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<'lcjs' | 'fallback'>('fallback');
  const payload = useMemo(() => JSON.stringify({ series, yMax }), [series, yMax]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let chart: { dispose: () => void } | null = null;

    void (async () => {
      try {
        const [lc, theme, mod] = await Promise.all([getLcFactory(), darkTheme(), loadLcjs()]);
        if (disposed) return;
        if (!lc || !theme || !mod) {
          setMode('fallback');
          return;
        }
        const xy = lc.ChartXY({ container: el, theme, animationsEnabled: false });
        xy.setTitle('').setPadding({ left: 4, right: 10, top: 4, bottom: 4 });
        if (yMax != null) xy.getDefaultAxisY().setInterval({ start: 0, end: yMax, stopAxisAfter: false });
        const { SolidFill, ColorHEX, SolidLine } = mod;
        for (const s of series) {
          const line = xy
            .addPointLineAreaSeries()
            .setName(s.name ?? s.id)
            .setStrokeStyle(new SolidLine({ thickness: 2, fillStyle: new SolidFill({ color: ColorHEX(s.color) }) }))
            .setAreaFillStyle(new SolidFill({ color: ColorHEX(s.color).setA(30) }));
          if (s.points.length) {
            line.appendSamples({
              xValues: s.points.map((p) => p.x),
              yValues: s.points.map((p) => p.y),
            });
          }
        }
        chart = xy;
        if (!disposed && el.clientHeight > 0) setMode('lcjs');
      } catch (err) {
        console.warn('[lcjs] ChartXY 失敗，改用 SVG', err);
        if (!disposed) setMode('fallback');
      }
    })();

    return () => {
      disposed = true;
      chart?.dispose();
    };
  }, [payload, series, yMax]);

  return (
    <div className="relative w-full" style={{ height, minHeight: height }}>
      {mode === 'fallback' ? <FallbackLine series={series} height={height} /> : null}
      <div
        ref={host}
        className={mode === 'lcjs' ? 'h-full w-full' : 'pointer-events-none absolute inset-0 opacity-0'}
        style={{ minHeight: height }}
      />
    </div>
  );
}
