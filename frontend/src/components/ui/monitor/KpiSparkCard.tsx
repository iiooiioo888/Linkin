import './monitor.css';

export function KpiSparkCard({
  label,
  value,
  unit,
  spark,
  accent,
}: {
  label: string;
  value: string | number;
  unit?: string;
  spark?: number[];
  accent?: boolean;
}) {
  const bars = spark ?? [];
  const max = bars.length ? Math.max(...bars, 1) : 1;

  return (
    <div className="mon-kpi-spark">
      <div>
        <p className="mon-kpi-spark__label">{label}</p>
        <p className={`mon-kpi-spark__value${accent ? ' mon-kpi-spark__value--accent' : ''}`}>
          {value}
          {unit ? <span className="ml-0.5 text-[0.5em] text-[var(--console-sub)]">{unit}</span> : null}
        </p>
      </div>
      {bars.length > 0 ? (
        <div className="mon-kpi-spark__bars" aria-hidden>
          {bars.map((v, i) => (
            <span
              key={i}
              className={`mon-kpi-spark__bar${accent && i === bars.length - 1 ? ' mon-kpi-spark__bar--accent' : v > 0 ? ' mon-kpi-spark__bar--on' : ''}`}
              style={{ height: `${Math.max(15, (v / max) * 100)}%` }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
