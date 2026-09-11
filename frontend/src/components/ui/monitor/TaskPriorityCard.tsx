import type { ReactNode } from 'react';
import './monitor.css';

export function TaskPriorityCard({
  priority,
  title,
  meta,
  children,
  active,
  onClick,
}: {
  priority: 'p1' | 'p2' | 'p3';
  title: string;
  meta?: ReactNode;
  children?: ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`mon-task-card mon-task-card--${priority}${active ? ' on' : ''}`}
    >
      <p className="mon-task-card__title truncate">{title}</p>
      {meta ? <div className="mon-task-card__meta">{meta}</div> : null}
      {children}
    </Tag>
  );
}
