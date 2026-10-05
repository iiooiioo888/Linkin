import { useTranslation } from 'react-i18next';
import type { L0Snapshot } from '../../../types';
import './monitor.css';

export function MonitorL0StatusChip({
  snapshot,
  onClick,
}: {
  snapshot: L0Snapshot | null;
  onClick: () => void;
}) {
  const { t } = useTranslation();
  if (!snapshot) return null;

  const radar = snapshot.radar;
  const pressure = Math.round((radar?.pressure ?? 0) * 100);
  const modeLabel = radar?.energy_save ? t('monitor.l0EnergySave') : t('monitor.l0PressureNormal');

  return (
    <button type="button" className="mon-l0-chip" onClick={onClick}>
      <span className="mon-l0-chip__title">{t('monitor.l0Situation')}</span>
      <span className="mon-l0-chip__mode">{modeLabel}</span>
      <span className="mon-l0-chip__pct font-mono tabular-nums">{t('monitor.l0PressurePct', { pct: pressure })}</span>
    </button>
  );
}
