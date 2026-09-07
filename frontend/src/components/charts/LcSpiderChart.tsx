import { useEffect, useMemo, useRef, useState } from 'react';
import { darkTheme, getLcFactory } from '../../lib/lcjsHost';

export type SpiderPoint = { axis: string; value: number };

function FallbackSpider({ points, height, max }: { points: SpiderPoint[]; height: number; max: number }) {
  const cx = 120;
  const cy = 110;
  const r = 78;
  const n = Math.max(3, points.length);
  const ring = (scale: number) =>
    points
      .map((_, i) => {
        const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
        return `${cx + Math.cos(a) * r * scale},${cy + Math.sin(a) * r * scale}`;
      })
      .join(' ');
  const poly = points
    .map((p, i) => {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
      const s = Math.max(0, Math.min(1, p.value / max));
      return `${cx + Math.cos(a) * r * s},${cy + Math.sin(a) * r * s}`;
    })
    .join(' ');
  return (
    <svg viewBox="0 0 240 220" className="mx-auto" style={{ height }} role="img" aria-label="雷達圖">
      <polygon points={ring(1)} fill="none" stroke="rgba(255,255,255,0.1)" />
      <polygon points={ring(0.5)} fill="none" stroke="rgba(255,255,255,0.08)" />
      <polygon points={poly} fill="rgba(0,122,255,0.28)" stroke="#007AFF" strokeWidth="2" />
      {points.map((p, i) => {
        const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
        return (
          <text
            key={p.axis}
            x={cx + Math.cos(a) * 96}
            y={cy + Math.sin(a) * 96}
            textAnchor="middle"
            fill="#AEAEB2"
            fontSize="11"
          >
            {p.axis}
          </text>
        );
      })}
    </svg>
  );
}

export default function LcSpiderChart({
  points,
  height = 220,
  max = 10,
}: {
  points: SpiderPoint[];
  height?: number;
  max?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<'lcjs' | 'fallback'>('lcjs');
  const payload = useMemo(() => JSON.stringify({ points, max }), [points, max]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let chart: { dispose: () => void } | null = null;

    void (async () => {
      const [lc, theme] = await Promise.all([getLcFactory(), darkTheme()]);
      if (disposed) return;
      if (!lc || !theme) {
        setMode('fallback');
        return;
      }
      setMode('lcjs');
      const spider = lc.Spider({ container: el, theme, animationsEnabled: false });
      spider.setTitle('');
      for (const p of points) {
        if (!spider.hasAxis(p.axis)) spider.addAxis(p.axis).setInterval({ start: 0, end: max });
      }
      spider.addSeries().setName('score').addPoints(...points);
      chart = spider;
    })();

    return () => {
      disposed = true;
      chart?.dispose();
    };
  }, [payload, points, max]);

  if (mode === 'fallback') {
    return <FallbackSpider points={points} height={height} max={max} />;
  }
  return <div ref={host} className="h-full w-full" style={{ minHeight: height }} />;
}
