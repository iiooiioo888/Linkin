import type { ReactNode } from 'react';
import './monitor.css';

export function MonitorPanel({
  title,
  accessory,
  className = '',
  bodyClassName = '',
  scroll = false,
  children,
}: {
  title: string;
  accessory?: ReactNode;
  className?: string;
  bodyClassName?: string;
  scroll?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`mon-panel ${className}`.trim()}>
      <header className="mon-panel__head">
        <h2 className="mon-panel__title">{title}</h2>
        {accessory ? <div className="mon-panel__accessory">{accessory}</div> : null}
      </header>
      <div
        className={`mon-panel__body${scroll ? ' mon-panel__body--scroll' : ''} ${bodyClassName}`.trim()}
      >
        {children}
      </div>
    </section>
  );
}
