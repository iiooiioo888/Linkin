/**
 * 控制台 zinc + indigo token — 與 index.css :root --console-* 同步，供 TS／圖表使用。
 */
export const consoleColors = {
  bg: '#0e0e10',
  sidebar: '#131316',
  card: '#18181b',
  cardHi: '#1f1f23',
  line: '#2a2a30',
  lineHi: '#3f3f46',
  ink: '#e4e4e7',
  sub: '#a1a1aa',
  faint: '#52525b',
  accent: '#6366f1',
  accentSoft: '#818cf8',
  green: '#34d399',
  blue: '#38bdf8',
  amber: '#fbbf24',
  danger: '#f87171',
} as const;

/** ECharts／圓餅／柱狀圖預設色序 */
export const CHART_PALETTE = [
  consoleColors.accent,
  consoleColors.blue,
  consoleColors.green,
  consoleColors.amber,
  consoleColors.sub,
] as const;

export const statusClasses = {
  good: 'console-status-green',
  warn: 'console-status-amber',
  error: 'console-status-danger',
  info: 'console-status-blue',
  accent: 'console-status-accent',
} as const;

export function healthTone(status: string): string {
  if (status === 'healthy') return statusClasses.good;
  if (status === 'degraded') return statusClasses.warn;
  return statusClasses.error;
}
