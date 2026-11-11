/**
 * 角色狀態圖示（✓／✗／脈動點）。
 */

import type { RoleStatus } from './types';

export function RoleIcon({ status }: { status: RoleStatus }) {
  if (status === 'done') return <span className="text-green-400">✓</span>;
  if (status === 'failed') return <span className="text-red-400">✗</span>;
  if (status === 'active') return <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-blue-400 align-middle" />;
  if (status === 'waiting') return <span className="inline-block h-2 w-2 rounded-full bg-yellow-400/80 align-middle" />;
  return null;
}
