import type { ReactNode } from 'react';
import './monitor.css';

/** LiveBoard 內狀態列（非第二道 48px 頂欄）：離線／操作／時間 */
export function MonitorStatusStrip({
  leading,
  actions,
  meta,
}: {
  leading?: ReactNode;
  actions?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <div className="mon-live-status" role="status">
      <div className="mon-live-status__leading">{leading}</div>
      <div className="mon-live-status__tail">
        {actions}
        {meta ? <div className="mon-live-status__meta">{meta}</div> : null}
      </div>
    </div>
  );
}
