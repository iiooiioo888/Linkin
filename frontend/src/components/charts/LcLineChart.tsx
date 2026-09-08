/**
 * 純 SVG 折線圖（深色主題）。已移除 LightningChart JS 依賴。
 * 支援多序列、面積填充、網格與圖例。
 */
import { useMemo } from 'react';

export type LineSeriesInput = {
  id: string;
  name?: string;
  color: string;
  points: Array<{ x: number; y: number }>;
};

const W = 640;
const PAD = { top: 10, right: 12, bottom: 18, left: 40 };

export default function LcLineChart({
  series,
  height = 180,
  yMax,
}: {
  series: LineSeriesInput[];
  height?: number;
  yMax?: number;
}) {
  const H = Math.max(80, height);
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const { minX, spanX, minY, spanY, ticks } = useMemo(() => {
    const allX = series.flatMap((s) => s.points.map((p) => p.x));
    const allY = series.flatMap((s) => s.points.map((p) => p.y));
    const loY = allY.length ? Math.min(...allY, 0) : 0;
    const hiY = yMax != null ? yMax : allY.length ? Math.max(...allY) : 1;
    const loX = allX.length ? Math.min(...allX) : 0;
    const hiX = allX.length ? Math.max(...allX) : loX + 1;
    const sy = hiY - loY || Math.abs(hiY) || 1;
    const sx = hiX - loX || 1;
    const t: number[] = [];
    for (let i = 0; i <= 4; i += 1) t.push(loY + (sy * i) / 4);
    return { minX: loX, spanX: sx, minY: loY, spanY: sy, ticks: t };
  }, [series, yMax]);

  const px = (x: number) => PAD.left + ((x - minX) / spanX) * innerW;
  const py = (y: number) => PAD.top + innerH - ((y - minY) / spanY) * innerH;

  const hasData = series.some((s) => s.points.length > 1);
  const fmt = (v: number) =>
    Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-full w-full"
      style={{ minHeight: height }}
      role="img"
      aria-label="折線圖"
      preserveAspectRatio="none"
    >
      {/* 水平網格 + Y 軸刻度 */}
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} y1={py(t)} x2={W - PAD.right} y2={py(t)} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
          <text x={PAD.left - 6} y={py(t) + 3} textAnchor="end" fontSize="9" fill="#62666d" fontFamily="ui-monospace, monospace">
            {fmt(t)}
          </text>
        </g>
      ))}
      {!hasData ? (
        <text x={W / 2} y={H / 2} textAnchor="middle" fontSize="11" fill="#62666d">
          尚無資料
        </text>
      ) : (
        series.map((s) => {
          if (!s.points.length) return null;
          const line = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${px(p.x)} ${py(p.y)}`).join(' ');
          const area =
            s.points.length > 1
              ? `${line} L ${px(s.points[s.points.length - 1].x)} ${py(minY)} L ${px(s.points[0].x)} ${py(minY)} Z`
              : '';
          return (
            <g key={s.id}>
              {area ? <path d={area} fill={s.color} opacity="0.1" /> : null}
              <path d={line} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
              {s.points.length === 1 ? <circle cx={px(s.points[0].x)} cy={py(s.points[0].y)} r="2.5" fill={s.color} /> : null}
            </g>
          );
        })
      )}
      {/* 圖例（多序列時） */}
      {series.length > 1
        ? series.map((s, i) => (
            <g key={`lg-${s.id}`} transform={`translate(${PAD.left + i * 110}, ${H - 5})`}>
              <rect x="0" y="-6" width="10" height="3" rx="1.5" fill={s.color} />
              <text x="14" y="0" fontSize="9" fill="#8E8E93">
                {s.name ?? s.id}
              </text>
            </g>
          ))
        : null}
    </svg>
  );
}
