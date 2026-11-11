/**
 * 角色指標帶：延遲、P95、成功率、容量、Token I/O 與 SLA。
 */

import type { RoleAgent } from '../../types';
import { blankMetrics } from '../../lib/agentUi';

export function RoleStatsStrip({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const success = m.success_rate ?? 0;
  const cap = `${agent.capacity_used ?? agent.executing}/${agent.max_parallel_work}`;
  const capPct = m.capacity_pct ?? 0;
  return (
    <div className="rd-stats">
      <div className="rd-stat">
        <span className="rd-stat-l">延遲</span>
        <span className="rd-stat-v">{Math.round(m.avg_latency_ms ?? 0)} ms</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">P95</span>
        <span className="rd-stat-v">{Math.round(m.p95_latency_ms ?? 0)} ms</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">成功率</span>
        <span className={`rd-stat-v ${success > 0 ? 'ok' : ''}`}>{success > 0 ? `${success}%` : '—'}</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">容量</span>
        <span className={`rd-stat-v ${capPct >= 80 ? 'wn' : ''}`}>{cap}</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">Token I/O</span>
        <span className="rd-stat-v">{m.tokens_in ?? 0} / {m.tokens_out ?? 0}</span>
      </div>
      <div className="rd-stat">
        <span className="rd-stat-l">SLA</span>
        <span className={`rd-stat-v ${(m.sla_breaches ?? 0) > 0 ? 'er' : ''}`}>{m.sla_breaches ?? 0}</span>
      </div>
    </div>
  );
}
