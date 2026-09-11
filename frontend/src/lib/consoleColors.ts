/**
 * 控制台軟色調 token — 與 index.css :root --console-* 同步，供 TS／圖表使用。
 */
export const consoleColors = {
  bg: '#0a0a0a',
  sidebar: '#0d0d0d',
  card: '#141414',
  cardHi: '#1a1a1a',
  line: '#2a2a2a',
  lineHi: '#3a3a3a',
  ink: '#e8e8e8',
  sub: '#8a8a8a',
  faint: '#555555',
  accent: '#c98a7a',
  green: '#6d9b7c',
  blue: '#7a8fad',
  amber: '#c4a574',
  danger: '#9a7068',
} as const;

/** ECharts／圓餅／柱狀圖預設色序（低飽和） */
export const CHART_PALETTE = [
  consoleColors.blue,
  consoleColors.sub,
  consoleColors.green,
  consoleColors.amber,
  consoleColors.faint,
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
