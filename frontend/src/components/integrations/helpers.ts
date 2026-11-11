/**
 * 整合面板共用樣式常數與健康狀態 helpers。
 */
import type { IntegrationStatus } from '../../api/integrations';
import { consoleLayout } from '../ui/ConsoleLayout';

export const inputCls =
  'w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[var(--console-ink)] outline-none focus:border-[var(--console-blue)]/50';
export const btnCls =
  'rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2.5 py-1 text-[11px] text-[var(--console-sub)] hover:text-[var(--console-ink)] disabled:opacity-40';
export const btnPrimaryCls =
  'rounded-xl border border-[var(--console-blue)]/40 bg-[var(--console-blue)]/10 px-2.5 py-1 text-[11px] console-status-blue disabled:opacity-40';
export const cardCls = consoleLayout.insetCard;

export function healthTone(item: IntegrationStatus): string {
  if (!item.enabled) return 'text-[var(--console-faint)]';
  if (item.health?.ok === false) return 'console-status-danger';
  return 'console-status-green';
}

export function healthLabel(item: IntegrationStatus): string {
  if (!item.enabled) return '已停用';
  if (item.health?.ok === false) return item.health.reason_code || '不可達';
  const ms = item.health?.latency_ms;
  return typeof ms === 'number' ? `健康 · ${Math.round(ms)}ms` : '健康';
}
