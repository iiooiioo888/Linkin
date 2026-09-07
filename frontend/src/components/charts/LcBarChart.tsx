import { useEffect, useMemo, useRef, useState } from 'react';
import { darkTheme, getLcFactory } from '../../lib/lcjsHost';

export type BarGroup = { subCategory: string; values: number[] };

function FallbackBars({
  categories,
  groups,
  height,
}: {
  categories: string[];
  groups: BarGroup[];
  height: number;
}) {
  const max = Math.max(1, ...groups.flatMap((g) => g.values));
  return (
    <div className="flex h-full items-end gap-3 px-2" style={{ minHeight: height }}>
      {categories.map((cat, i) => (
        <div key={cat} className="flex min-w-0 flex-1 flex-col items-center gap-1">
          <div className="flex h-full w-full items-end justify-center gap-0.5">
            {groups.map((g) => (
              <div
                key={g.subCategory}
                className="w-3 rounded-t bg-[#007AFF]"
                style={{
                  height: `${((g.values[i] ?? 0) / max) * 100}%`,
                  background: g.subCategory.includes('A') ? 'rgba(142,142,147,0.7)' : '#007AFF',
                }}
              />
            ))}
          </div>
          <span className="truncate text-[10px] text-[#8E8E93]">{cat}</span>
        </div>
      ))}
    </div>
  );
}

export default function LcBarChart({
  categories,
  groups,
  height = 260,
}: {
  categories: string[];
  groups: BarGroup[];
  height?: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<'lcjs' | 'fallback'>('lcjs');
  const payload = useMemo(() => JSON.stringify({ categories, groups }), [categories, groups]);

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
      const bar = lc.BarChart({ container: el, theme, animationsEnabled: false });
      bar.setTitle('');
      if (groups.length <= 1) {
        bar.setData(categories.map((category, i) => ({ category, value: groups[0]?.values[i] ?? 0 })));
      } else {
        bar.setDataGrouped(categories, groups);
      }
      chart = bar;
    })();

    return () => {
      disposed = true;
      chart?.dispose();
    };
  }, [payload, categories, groups]);

  if (mode === 'fallback') {
    return <FallbackBars categories={categories} groups={groups} height={height} />;
  }
  return <div ref={host} className="h-full w-full" style={{ minHeight: height }} />;
}
