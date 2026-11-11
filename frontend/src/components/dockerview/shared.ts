/**
 * Docker 面板共通常量與格式化：刷新間隔、狀態／健康色票、費率與費用格式化。
 */

// ═══════════════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════════════

export const REFRESH_INTERVAL = 8000; // 8 秒自动刷新

export const STATUS_COLORS: Record<string, string> = {
  running: 'bg-green-500/20 console-status-green',
  exited: 'bg-red-500/20 console-status-danger',
  restarting: 'bg-yellow-500/20 text-yellow-300',
  paused: 'bg-gray-500/20 text-[var(--console-faint)]',
  removing: 'bg-red-500/20 console-status-danger',
};

export const HEALTH_COLORS: Record<string, string> = {
  healthy: 'bg-green-500/20 console-status-green',
  unhealthy: 'bg-red-500/20 console-status-danger',
  starting: 'bg-yellow-500/20 text-yellow-300',
  unknown: 'bg-gray-500/20 text-[var(--console-faint)]',
};

export function statusLabel(status: string): string {
  if (status.startsWith('Up')) return 'running';
  if (status.startsWith('Exited')) return 'exited';
  if (status.startsWith('Restarting')) return 'restarting';
  return status.toLowerCase();
}

export function formatRate(rate: number): string {
  return `$${rate.toFixed(3)}/h`;
}

export function calcCost(uptimeSeconds: number, rate: number): number {
  return (uptimeSeconds / 3600) * rate;
}

export function formatCost(amount: number): string {
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}
