import { useTranslation } from 'react-i18next';
import type { L0Snapshot } from '../../../types';
import './monitor.css';

function resolveL0PressurePct(snapshot: L0Snapshot | null): number | null {
  if (!snapshot) return null;
  const raw = snapshot.radar?.pressure;
  if (raw == null || typeof raw !== 'number' || !Number.isFinite(raw)) return null;
  return Math.round(raw * 100);
}

export function MonitorL0StatusChip({
  snapshot,
  onClick,
}: {
  snapshot: L0Snapshot | null;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  const pressurePct = resolveL0PressurePct(snapshot);
  const unknown = pressurePct === null;

  if (unknown) {
    return (
      <button type="button" className="mon-l0-chip mon-l0-chip--unknown" onClick={onClick}>
        <span className="mon-l0-chip__label">{t('monitor.l0Unknown')}</span>
      </button>
    );
  }

  const radar = snapshot?.radar;
  const modeLabel = radar?.energy_save ? t('monitor.l0EnergySave') : t('monitor.l0PressureNormal');

  return (
    <button type="button" className="mon-l0-chip" onClick={onClick}>
      <span className="mon-l0-chip__title">{t('monitor.l0Situation')}</span>
      <span className="mon-l0-chip__mode">{modeLabel}</span>
      <span className="mon-l0-chip__pct font-mono tabular-nums">
        {t('monitor.l0PressurePct', { pct: pressurePct })}
      </span>
    </button>
  );
}
