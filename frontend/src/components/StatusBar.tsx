/**
 * StatusBar — 極簡底部狀態列。
 */
import { useEffect, useState } from 'react';
import { fetchDockerBudget, fetchDockerStatus } from '../api/client';
import type { DockerBudget, DockerStatus } from '../types';
import { useIntegrationsStatus } from '../hooks/useIntegrationsStatus';
import { jumpToIntegration, summarizeIntegrations } from '../lib/integrationsUi';
import { useMonitorStore } from '../stores/monitorStore';

interface StatusBarProps {
  llmConfigured: boolean | null;
  taskCount: number;
  memoryCount: number;
}

function formatCost(amount: number): string {
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

function Dot({ tone }: { tone: 'ok' | 'warn' | 'err' | 'idle' }) {
  const cls =
    tone === 'ok'
      ? 'apple-dot apple-dot--ok'
      : tone === 'warn'
        ? 'apple-dot apple-dot--warn'
        : tone === 'err'
          ? 'apple-dot apple-dot--err'
          : 'apple-dot';
  return <span className={cls} />;
}

export default function StatusBar({ llmConfigured, taskCount, memoryCount }: StatusBarProps) {
  const [dockerStatus, setDockerStatus] = useState<DockerStatus | null>(null);
  const [dockerBudget, setDockerBudget] = useState<DockerBudget | null>(null);
  const llmOps = useMonitorStore((s) => s.llmOps);
  const apiReady = (llmOps?.api_routes ?? []).filter((r) => r.enabled && r.configured).length;
  const { items: integItems } = useIntegrationsStatus(20000);
  const integ = summarizeIntegrations(integItems);
  const integTone =
    integ.degraded > 0 ? 'warn' : integ.enabled > 0 ? 'ok' : ('idle' as const);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const [status, budget] = await Promise.all([fetchDockerStatus(), fetchDockerBudget()]);
        if (!cancelled) {
          setDockerStatus(status);
          setDockerBudget(budget);
        }
      } catch {
        if (!cancelled) {
          setDockerStatus(null);
          setDockerBudget(null);
        }
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 15000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const dockerHealthy = dockerStatus?.health?.all_healthy
    ? Object.values(dockerStatus.health.services).filter((s) => s.healthy).length
    : 0;
  const dockerTotal = dockerStatus?.health?.services
    ? Object.keys(dockerStatus.health.services).length
    : 0;

  const totalCost = dockerBudget?.total_docker_cost ?? 0;

  const llmTone =
    llmConfigured === null ? 'idle' : llmConfigured ? 'ok' : ('warn' as const);
  const dockerTone =
    dockerStatus === null
      ? 'idle'
      : !dockerStatus.available
        ? 'err'
        : dockerStatus.health?.all_healthy
          ? 'ok'
          : 'warn';

  return (
    <footer className="apple-status-bar">
      <div className="flex min-w-0 items-center gap-3 overflow-x-auto">
        <span className="apple-status-item">
          <Dot tone={llmTone} />
          <a href="#/monitor/llm" className="hover:text-[#F5F5F7]">
            {llmConfigured === false
              ? 'LLM 未配置'
              : apiReady > 0
                ? `API ${apiReady}`
                : '就緒'}
          </a>
        </span>

        <span className="apple-status-item hidden sm:inline-flex">
          <a href="#/monitor/agents" className="hover:text-[#F5F5F7]">
            角色
          </a>
        </span>

        <span className="apple-status-item hidden md:inline-flex">
          <Dot tone={integTone} />
          <button
            type="button"
            className="hover:text-[#F5F5F7]"
            onClick={() => jumpToIntegration()}
            title="MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil"
          >
            整合 {integ.enabled}/{integ.total}
            {integ.degraded ? ` ·降${integ.degraded}` : ''}
          </button>
        </span>

        <span className="apple-status-item hidden sm:inline-flex">
          <Dot tone={dockerTone} />
          <span>
            {dockerStatus?.available ? `Docker ${dockerHealthy}/${dockerTotal}` : 'Docker —'}
          </span>
        </span>

        {dockerBudget?.available && totalCost > 0 && (
          <span className="apple-status-item apple-data hidden md:inline-flex">
            {formatCost(totalCost)}
          </span>
        )}

        <span className="apple-status-item apple-data ml-auto">
          {taskCount} 任務 · {memoryCount} 記憶
        </span>
      </div>
    </footer>
  );
}
