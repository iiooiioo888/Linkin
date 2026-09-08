/**
 * 純 SVG 長條圖（深色主題）。已移除 LightningChart JS 依賴。
 * 支援單組與分組（grouped）資料。
 */
import { useMemo } from 'react';

export type BarGroup = { subCategory: string; values: number[] };

const W = 640;
const PAD = { top: 10, right: 12, bottom: 24, left: 40 };
const PALETTE = ['#0A84FF', '#8E8E93', '#34C759', '#FF9F0A', '#BF5AF2', '#FF375F'];

export default function LcBarChart({
  categories,
  groups,
  height = 260,
}: {
  categories: string[];
  groups: BarGroup[];
  height?: number;
}) {
  const H = Math.max(120, height);
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const { max, ticks } = useMemo(() => {
    const m = Math.max(1, ...groups.flatMap((g) => g.values.map((v) => v || 0)));
    const t: number[] = [];
    for (let i = 0; i <= 4; i += 1) t.push((m * i) / 4);
    return { max: m, ticks: t };
  }, [groups]);

  const n = Math.max(1, categories.length);
  const groupW = innerW / n;
  const barPad = Math.min(10, groupW * 0.18);
  const gCount = Math.max(1, groups.length);
  const barW = Math.max(2, (groupW - barPad * 2) / gCount - 2);

  const fmt = (v: number) => (Math.abs(v) >= 1000 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(1));
  const yBase = PAD.top + innerH;

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-full w-full"
      style={{ minHeight: height }}
      role="img"
      aria-label="長條圖"
      preserveAspectRatio="none"
    >
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} y1={yBase - (t / max) * innerH} x2={W - PAD.right} y2={yBase - (t / max) * innerH} stroke="rgba(255,255,255,0.06)" />
          <text x={PAD.left - 6} y={yBase - (t / max) * innerH + 3} textAnchor="end" fontSize="9" fill="#62666d" fontFamily="ui-monospace, monospace">
            {fmt(t)}
          </text>
        </g>
      ))}
      {categories.map((cat, i) => (
        <g key={cat}>
          {groups.map((g, gi) => {
            const v = g.values[i] ?? 0;
            const h = Math.max(0, (v / max) * innerH);
            const x = PAD.left + i * groupW + barPad + gi * (barW + 2);
            return (
              <rect
                key={g.subCategory}
                x={x}
                y={yBase - h}
                width={barW}
                height={h}
                rx={2}
                fill={PALETTE[gi % PALETTE.length]}
                opacity={gCount > 1 && gi % 2 === 1 ? 0.75 : 1}
              >
                <title>{`${cat} · ${g.subCategory}: ${v}`}</title>
              </rect>
            );
          })}
          <text
            x={PAD.left + i * groupW + groupW / 2}
            y={H - 8}
            textAnchor="middle"
            fontSize="9.5"
            fill="#8E8E93"
          >
            {cat.length > 10 ? `${cat.slice(0, 9)}…` : cat}
          </text>
        </g>
      ))}
      {gCount > 1
        ? groups.map((g, gi) => (
            <g key={`lg-${g.subCategory}`} transform={`translate(${PAD.left + gi * 110}, ${PAD.top - 2})`}>
              <rect x="0" y="-6" width="10" height="6" rx="1.5" fill={PALETTE[gi % PALETTE.length]} />
              <text x="14" y="0" fontSize="9" fill="#8E8E93">
                {g.subCategory}
              </text>
            </g>
          ))
        : null}
    </svg>
  );
}
