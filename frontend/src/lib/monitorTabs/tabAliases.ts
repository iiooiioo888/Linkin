/**
 * 僅觀測別名（世界模組頁別名在 worldModules.MODULE_PAGE_ALIASES）。
 */
import type { MonitorTab } from '../../components/AppShell';

/** 僅觀測別名。世界模組頁別名在 worldModules.MODULE_PAGE_ALIASES。 */
export const CONSOLE_TAB_ALIASES: Record<string, MonitorTab> = {
  overview: 'live',
  balancer: 'live',
  task: 'tasks',
  pipeline: 'agents',
  dashboard: 'tasks',
  hub: 'ops',
  cloud: 'ops',
  docker: 'ops',
  billing: 'models',
  credits: 'models',
  wallet: 'models',
  usage: 'models',
  observe: 'models',
  checkpoints: 'ops',
  opc: 'metrics',
  dbpool: 'ops',
  routes: 'llm',
  l0: 'memory',
  context: 'context',
  ctx: 'context',
  dshcontext: 'context',
  integrate: 'integrations',
  integration: 'integrations',
  memos: 'integrations',
  openviking: 'integrations',
  weknora: 'integrations',
  yao: 'integrations',
  ouroboros: 'integrations',
  openpencil: 'integrations',
  grill: 'agents',
  /** Phase1 新路徑段 → MonitorTab */
  approvals: 'approvals',
  exec: 'exec',
  quota: 'quota',
  health: 'health',
  memory: 'memory',
};
export const MONITOR_TAB_ALIASES = CONSOLE_TAB_ALIASES;
