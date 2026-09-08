/**
 * 純 SVG 雷達圖（深色主題）。已移除 LightningChart JS 依賴。
 */
import { useMemo } from 'react';

export type SpiderPoint = { axis: string; value: number };

const CX = 120;
const CY = 110;
const R = 78;

export default function LcSpiderChart({
  points,
  height = 220,
  max = 10,
}: {
  points: SpiderPoint[];
  height?: number;
  max?: number;
}) {
  const n = Math.max(3, points.length);
  const angle = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n;

  const { rings, poly } = useMemo(() => {
    const ring = (scale: number) =>
      points
        .map((_, i) => `${CX + Math.cos(angle(i)) * R * scale},${CY + Math.sin(angle(i)) * R * scale}`)
        .join(' ');
    const p = points
      .map((pt, i) => {
        const s = Math.max(0, Math.min(1, pt.value / max));
        return `${CX + Math.cos(angle(i)) * R * s},${CY + Math.sin(angle(i)) * R * s}`;
      })
      .join(' ');
    return { rings: [ring(1), ring(0.75), ring(0.5), ring(0.25)], poly: p };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, max, n]);

  return (
    <svg
      viewBox="0 0 240 220"
      className="mx-auto"
      style={{ height }}
      role="img"
      aria-label="雷達圖"
    >
      {rings.map((r, i) => (
        <polygon key={i} points={r} fill="none" stroke="rgba(255,255,255,0.08)" />
      ))}
      {points.map((_, i) => (
        <line
          key={i}
          x1={CX}
          y1={CY}
          x2={CX + Math.cos(angle(i)) * R}
          y2={CY + Math.sin(angle(i)) * R}
          stroke="rgba(255,255,255,0.06)"
        />
      ))}
      <polygon points={poly} fill="rgba(0,122,255,0.28)" stroke="#007AFF" strokeWidth="2" />
      {points.map((p, i) => {
        const s = Math.max(0, Math.min(1, p.value / max));
        return (
          <circle
            key={p.axis}
            cx={CX + Math.cos(angle(i)) * R * s}
            cy={CY + Math.sin(angle(i)) * R * s}
            r="2.5"
            fill="#007AFF"
          >
            <title>{`${p.axis}: ${p.value}`}</title>
          </circle>
        );
      })}
      {points.map((p, i) => (
        <text
          key={`t-${p.axis}`}
          x={CX + Math.cos(angle(i)) * 96}
          y={CY + Math.sin(angle(i)) * 96}
          textAnchor="middle"
          fill="#AEAEB2"
          fontSize="11"
        >
          {p.axis}
        </text>
      ))}
    </svg>
  );
}
