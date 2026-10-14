/**
 * LiveBoard 首屏收斂：工作流下一步與異常彙整（純資料，便於單測）。
 */
import type { MonitorTab } from '../components/AppShell';
import type { AnimLiveFeed } from './animLive';

export interface WorkflowStep {
  n: string;
  label: string;
  hint: string;
  tab: MonitorTab;
  done: boolean;
  active?: boolean;
  onClick?: () => void;
}

export function buildWorkflowSteps(
  feed: AnimLiveFeed,
  onOpenTab?: (tab: MonitorTab) => void,
  onRoleDesk?: () => void,
): WorkflowStep[] {
  const routes = feed.llmOps?.api_routes ?? [];
  const apiReady =
    routes.some((r) => r.configured && r.enabled) || Boolean(feed.llmOps?.configured);
  const pinned = feed.agents.filter((a) => Boolean(a.preferred_model || a.preferred_provider)).length;
  const taskRunning =
    feed.runningTasks > 0 || (feed.summary?.running_company_tasks ?? 0) > 0;

  return [
    {
      n: '1',
      label: '配置 API',
      hint: apiReady ? `${routes.length || 1} 組可用` : '金鑰與模型目錄',
      tab: 'llm',
      done: apiReady,
    },
    {
      n: '2',
      label: '指定角色',
      hint: pinned ? `${pinned} 席已指定` : '模型與 Token',
      tab: 'agents',
      done: pinned > 0,
      onClick: onRoleDesk
        ? () => {
            onRoleDesk();
            onOpenTab?.('agents');
          }
        : undefined,
    },
    {
      n: '3',
      label: '執行任務',
      hint: taskRunning ? '進行中' : '佇列與進度',
      tab: 'tasks',
      done: !taskRunning && (feed.summary?.work_items_done ?? 0) > 0,
      active: taskRunning,
    },
    {
      n: '4',
      label: '計費用量',
      hint: 'AI 與 Docker 成本',
      tab: 'billing',
      done: false,
    },
  ];
}

export function pickNextWorkflowStep(steps: WorkflowStep[]): WorkflowStep | null {
  const active = steps.find((s) => s.active);
  if (active) return active;
  const next = steps.find((s) => !s.done);
  return next ?? null;
}

export type AnomalyTone = 'warn' | 'err' | 'info';

export interface LiveAnomaly {
  id: string;
  title: string;
  hint?: string;
  tone: AnomalyTone;
  tab?: MonitorTab;
  agentId?: string;
}

export function collectLiveAnomalies(input: {
  feed: AnimLiveFeed;
  connected: boolean;
  unhealthyKeys: number;
  capacityFull: boolean;
  cacheWarnText?: string;
}): LiveAnomaly[] {
  const { feed, connected, unhealthyKeys, capacityFull, cacheWarnText } = input;
  const out: LiveAnomaly[] = [];

  if (!connected) {
    out.push({
      id: 'offline',
      title: '離線資料',
      hint: 'Hub 未連線，顯示上次快照',
      tone: 'warn',
      tab: 'live',
    });
  }

  if (capacityFull && cacheWarnText) {
    out.push({
      id: 'cache-full',
      title: '快取容量已滿',
      hint: cacheWarnText.replace(/^⚠\s*/, ''),
      tone: 'warn',
      tab: 'metrics',
    });
  }

  if (unhealthyKeys > 0) {
    out.push({
      id: 'billing-keys',
      title: `${unhealthyKeys} 組金鑰異常`,
      hint: '請檢查 AI 用量與金鑰狀態',
      tone: 'err',
      tab: 'billing',
    });
  }

  const routes = feed.llmOps?.api_routes ?? [];
  const apiReady =
    routes.some((r) => r.configured && r.enabled) || Boolean(feed.llmOps?.configured);
  if (feed.llmOps && !apiReady) {
    out.push({
      id: 'api-missing',
      title: '尚未配置 API',
      hint: '完成金鑰與模型目錄後才能執行任務',
      tone: 'warn',
      tab: 'llm',
    });
  }

  for (const a of feed.agents) {
    if (a.status === 'error') {
      out.push({
        id: `agent-${a.id}`,
        title: `角色異常 · ${a.name}`,
        hint: '執行或佇列發生錯誤',
        tone: 'err',
        tab: 'agents',
        agentId: a.id,
      });
    }
  }

  const errAgents = out.filter((x) => x.id.startsWith('agent-'));
  if (errAgents.length > 5) {
    return out.filter((x) => !x.id.startsWith('agent-')).concat(errAgents.slice(0, 5));
  }

  return out;
}

/** 首屏視為「空任務」：無佇列任務且無執行中。 */
export function isLiveBoardTaskEmpty(feed: AnimLiveFeed, taskCount: number): boolean {
  const running =
    taskCount > 0 ||
    feed.runningTasks > 0 ||
    (feed.summary?.running_company_tasks ?? 0) > 0;
  return !running;
}
