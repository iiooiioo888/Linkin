import type { CSSProperties } from 'react';
import './monitor.css';

export type GaugeItem = { label: string; pct: number; color?: string };

export function ResourceGauges({ gauges, size = 48 }: { gauges: GaugeItem[]; size?: number }) {
  return (
    <div className="flex items-center justify-around gap-2">
      {gauges.map((g) => (
        <div key={g.label} className="mon-gauge">
          <div
            className="mon-gauge__ring"
            style={
              {
                width: size,
                height: size,
                '--gauge-pct': Math.min(100, Math.max(0, g.pct)),
                '--gauge-color': g.color ?? 'var(--console-accent)',
              } as CSSProperties
            }
          >
            <span className="mon-gauge__val">{g.pct}%</span>
          </div>
          <span className="mon-gauge__lbl">{g.label}</span>
        </div>
      ))}
    </div>
  );
}
