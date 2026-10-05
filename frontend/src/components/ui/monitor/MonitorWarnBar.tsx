import type { ReactNode } from 'react';
import './monitor.css';

export function MonitorWarnBar({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`mon-warn ${className}`.trim()}>{children}</div>;
}
