import type { DockerHealth } from '../../types';

/** 健康检查摘要栏 */
export function HealthBar({ health }: { health: DockerHealth }) {
  const total = Object.keys(health.services).length;
  const healthy = Object.values(health.services).filter((s) => s.healthy).length;
  const unhealthy = total - healthy;

  return (
    <div className="flex items-center gap-4 rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)]/80 px-4 py-2.5">
      <span className="text-xs font-medium text-[var(--console-faint)]">健康检查</span>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs">
          <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
          <span className="console-status-green">{healthy} 健康</span>
        </span>
        {unhealthy > 0 && (
          <span className="flex items-center gap-1.5 text-xs">
            <span className="inline-block h-2 w-2 rounded-full bg-red-400" />
            <span className="console-status-danger">{unhealthy} 异常</span>
          </span>
        )}
        <span className="text-xs text-[var(--console-faint)]">共 {total} 服务</span>
      </div>
      <span
        className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${
          health.all_healthy
            ? 'bg-green-500/20 console-status-green'
            : 'bg-red-500/20 console-status-danger'
        }`}
      >
        {health.all_healthy ? '全部健康' : '存在异常'}
      </span>
    </div>
  );
}
