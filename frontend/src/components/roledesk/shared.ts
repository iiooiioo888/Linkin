/**
 * 角色工作台共用小工具：進度環常數、角色縮寫、百分比與事件標籤。
 */

import { EVENT_LABELS } from '../TaskPanel';

export const RING = 2 * Math.PI * 15.5;

export function roleInitials(name: string): string {
  const latin = name.match(/[A-Za-z0-9]+/g);
  if (latin && latin.join('').length >= 2) return latin.join('').slice(0, 2).toUpperCase();
  return name.slice(0, 2);
}

export function pctBar(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(100, (value / max) * 100));
}

export function eventLabel(event: string): string {
  return EVENT_LABELS[event] ?? event.replace(/_/g, ' ');
}
