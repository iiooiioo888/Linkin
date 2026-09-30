/**
 * Minecraft 模組共用整頁骨架。只放有值的數字，缺資料不畫佔位。
 */
import type { ReactNode } from 'react';
import './minecraft.css';

export function McPage({ children, fill = false }: { children: ReactNode; fill?: boolean }) {
  return (
    <div className={`mc-page${fill ? ' is-fill' : ''}`}>
      {fill ? (
        <div className="mc-page__fill">{children}</div>
      ) : (
        <div className="mc-page__scroll">
          <div className="mc-page__inner">{children}</div>
        </div>
      )}
    </div>
  );
}

export function McHeader({
  title,
  lead,
  aside,
}: {
  title: string;
  lead?: string;
  aside?: ReactNode;
}) {
  return (
    <header className="mc-header">
      <div>
        <p className="mc-kicker">Minecraft</p>
        <h1 className="mc-title">{title}</h1>
        {lead ? <p className="mc-lead">{lead}</p> : null}
      </div>
      {aside ? <div className="mc-header__aside">{aside}</div> : null}
    </header>
  );
}

export function McMetrics({
  items,
}: {
  items: Array<{ label: string; value: string | number }>;
}) {
  if (!items.length) return null;
  return (
    <section className="mc-metrics" aria-label="現況">
      {items.map((item) => (
        <div key={item.label} className="mc-metric">
          <div className="mc-metric__value">{item.value}</div>
          <div className="mc-metric__label">{item.label}</div>
        </div>
      ))}
    </section>
  );
}

export function McPanel({
  title,
  hint,
  action,
  children,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mc-panel">
      <div className="mc-panel__head">
        <h2 className="mc-panel__title">{title}</h2>
        {action ?? (hint ? <span className="mc-panel__hint">{hint}</span> : null)}
      </div>
      {children}
    </section>
  );
}

export function McLinks({
  links,
}: {
  links: Array<{ href: string; label: string; primary?: boolean }>;
}) {
  return (
    <div className="mc-actions">
      {links.map((link) => (
        <a key={link.href + link.label} href={link.href} className={`mc-link${link.primary ? ' is-primary' : ''}`}>
          {link.label}
        </a>
      ))}
    </div>
  );
}
