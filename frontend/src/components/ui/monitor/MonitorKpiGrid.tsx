import type { ReactNode } from 'react';
import './monitor.css';

export function MonitorKpiGrid({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`mon-kpi-grid ${className}`.trim()}>{children}</div>;
}
