import './monitor.css';

const TONE_CLASS = {
  ok: 'mon-status-dot__mark--ok',
  warn: 'mon-status-dot__mark--warn',
  err: 'mon-status-dot__mark--err',
  info: 'mon-status-dot__mark--info',
  idle: 'mon-status-dot__mark--idle',
} as const;

export type MonitorStatusTone = keyof typeof TONE_CLASS;

export function MonitorStatusDot({
  tone = 'idle',
  label,
}: {
  tone?: MonitorStatusTone;
  label: string;
}) {
  return (
    <span className="mon-status-dot">
      <span className={`mon-status-dot__mark ${TONE_CLASS[tone]}`} />
      {label}
    </span>
  );
}
