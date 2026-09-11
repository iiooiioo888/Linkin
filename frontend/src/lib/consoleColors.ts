/**
 * 控制台 gold/dark v3 token — 與 index.css :root --console-* 同步，供 TS／圖表使用。
 */
export const consoleColors = {
  bg: '#08080a',
  sidebar: '#0c0c0f',
  card: '#121216',
  cardHi: '#18181d',
  line: '#1f1f25',
  lineHi: '#2a2a32',
  ink: '#e6e6ea',
  sub: '#82828c',
  faint: '#45454e',
  dim: '#2e2e36',
  accent: '#c9a961',
  accentSoft: '#6e5a32',
  green: '#6fa87f',
  greenDk: '#2e4a38',
  blue: '#7a92b8',
  blueDk: '#2e3d52',
  amber: '#c9a961',
  danger: '#b88080',
  dangerDk: '#4a2e2e',
  purple: '#9184b5',
  purpleDk: '#3d3452',
  cyan: '#7aa8b8',
  cyanDk: '#2e4450',
} as const;

/** ECharts／圓餅／柱狀圖預設色序 */
export const CHART_PALETTE = [
  consoleColors.accent,
  consoleColors.blue,
  consoleColors.green,
  consoleColors.purple,
  consoleColors.cyan,
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
