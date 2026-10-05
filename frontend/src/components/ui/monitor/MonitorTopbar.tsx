import type { ReactNode } from 'react';
import './monitor.css';

export type MonitorTopbarNavItem = {
  key: string;
  label: string;
  active?: boolean;
  onClick?: () => void;
};

export function MonitorTopbar({
  brand,
  nav = [],
  meta,
  actions,
}: {
  brand: ReactNode;
  nav?: MonitorTopbarNavItem[];
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mon-topbar">
      <div className="mon-topbar__brand">{brand}</div>
      {nav.length > 0 ? (
        <nav className="mon-topbar__nav" aria-label="監控導覽">
          {nav.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`mon-topbar__nav-link${item.active ? ' on' : ''}`}
              onClick={item.onClick}
            >
              {item.label}
            </button>
          ))}
        </nav>
      ) : null}
      <div className="mon-topbar__tail">
        {actions}
        {meta ? <div className="mon-topbar__meta">{meta}</div> : null}
      </div>
    </header>
  );
}
