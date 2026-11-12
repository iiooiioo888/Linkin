/**
 * 角色桌面共用常數與小工具：看板欄位、導覽區塊、狀態與事件等級。
 */

import type { WorkItemColumnKey } from '../../lib/agentUi';
import type { RoleAgent } from '../../types';

export const KANBAN_COLUMNS = [
  { key: 'queue' as WorkItemColumnKey, label: '待辦' },
  { key: 'executing' as WorkItemColumnKey, label: '進行中' },
  { key: 'done' as WorkItemColumnKey, label: '已完成' },
];

export const LEFT_SECTIONS = [
  { id: 'role-overview', label: '概覽' },
  { id: 'role-execution', label: '執行' },
  { id: 'role-system', label: '組織' },
];

export function isLive(agent: RoleAgent): boolean {
  return agent.status === 'busy' || agent.status === 'waiting';
}

export function eventLevel(event: string): 'info' | 'warn' | 'err' {
  if (event.includes('error') || event.includes('fail')) return 'err';
  if (event.includes('warn') || event.includes('block')) return 'warn';
  return 'info';
}
