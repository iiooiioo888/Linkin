/**
 * StatusBar — 可展開的狀態膠囊（預設精簡，避免底欄極小字塞滿指標）。
 */
import { useEffect, useRef, useState } from 'react';
import { fetchDockerBudget, fetchDockerStatus } from '../api/client';
import type { DockerBudget, DockerStatus } from '../types';
import { useIntegrationsStatus } from '../hooks/useIntegrationsStatus';
import { useIsMobile } from '../hooks/useMediaQuery';
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
  const isMobile = useIsMobile();
  const [expanded, setExpanded] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
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

  useEffect(() => {
    if (!expanded) return;
    const onDoc = (e: MouseEvent) => {
      if (!panelRef.current?.contains(e.target as Node)) setExpanded(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [expanded]);

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

  const summaryLabel =
    llmConfigured === false
      ? 'LLM 未配置'
      : apiReady > 0
        ? `API ${apiReady}`
        : '系統狀態';

  const hasAlert =
    llmConfigured === false ||
    integ.degraded > 0 ||
    (dockerStatus?.available && !dockerStatus.health?.all_healthy);

  return (
    <footer
      className={`status-shell ${isMobile ? 'status-shell--mobile' : 'status-shell--desktop'}`}
      ref={panelRef}
    >
      <button
        type="button"
        className={`status-capsule${expanded ? ' is-open' : ''}${hasAlert ? ' has-alert' : ''}`}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls="status-capsule-panel"
      >
        <Dot tone={llmTone} />
        <span className="status-capsule__label">{summaryLabel}</span>
        {taskCount > 0 ? (
          <span className="status-capsule__meta">{taskCount} 任務</span>
        ) : null}
        <span className="status-capsule__chev" aria-hidden>{expanded ? '▴' : '▾'}</span>
      </button>

      {expanded ? (
        <div id="status-capsule-panel" className="status-capsule-panel" role="region" aria-label="系統狀態詳情">
          <div className="status-capsule-panel__grid">
            <span className="status-capsule-row">
              <Dot tone={llmTone} />
              <a href="#/monitor/llm" className="status-capsule-link" onClick={() => setExpanded(false)}>
                {llmConfigured === false
                  ? 'LLM 未配置 — 前往 API 路由'
                  : apiReady > 0
                    ? `API 路由 ${apiReady} 條就緒`
                    : 'API 路由'}
              </a>
            </span>

            <span className="status-capsule-row">
              <a href="#/monitor/agents" className="status-capsule-link" onClick={() => setExpanded(false)}>
                角色工作台
              </a>
            </span>

            <span className="status-capsule-row">
              <Dot tone={integTone} />
              <button
                type="button"
                className="status-capsule-link"
                onClick={() => {
                  jumpToIntegration();
                  setExpanded(false);
                }}
              >
                工具 {integ.enabled}/{integ.total}
                {integ.degraded ? ` · 異常 ${integ.degraded}` : ''}
              </button>
            </span>

            <span className="status-capsule-row">
              <Dot tone={dockerTone} />
              <span>
                {dockerStatus?.available ? `Docker ${dockerHealthy}/${dockerTotal}` : 'Docker 未連線'}
              </span>
            </span>

            {dockerBudget?.available && totalCost > 0 ? (
              <span className="status-capsule-row apple-data">{formatCost(totalCost)}</span>
            ) : null}

            <span className="status-capsule-row status-capsule-row--emph">
              {taskCount} 任務 · {memoryCount} 記憶
            </span>
          </div>
        </div>
      ) : null}
    </footer>
  );
}
