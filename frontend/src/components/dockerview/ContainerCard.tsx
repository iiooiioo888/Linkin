/**
 * 容器卡片：狀態、資源使用、按時計費與重啟／停止／啟動二次確認。
 */

import { useState } from 'react';
import type { DockerContainer, DockerContainerStats } from '../../types';
import {
  HEALTH_COLORS,
  STATUS_COLORS,
  calcCost,
  formatCost,
  formatRate,
  statusLabel,
} from './shared';

// ═══════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════

/** 容器卡片 */
export function ContainerCard({
  container,
  stats,
  isBusy,
  hourlyRate,
  onRestart,
  onStop,
  onStart,
  onViewLogs,
}: {
  container: DockerContainer;
  stats?: DockerContainerStats;
  isBusy: boolean;
  hourlyRate: number;
  onRestart: () => void;
  onStop: () => void;
  onStart: () => void;
  onViewLogs: () => void;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);

  const statusKey = statusLabel(container.status);
  const statusColor = STATUS_COLORS[statusKey] || 'bg-gray-500/20 text-[var(--console-faint)]';
  const healthColor = HEALTH_COLORS[container.health] || 'bg-gray-500/20 text-[var(--console-faint)]';

  // 是否可以被操作（非 stub 容器）
  const isReal = container.service !== '_docker_unavailable';
  const isRunning = statusKey === 'running';
  const isStopped = statusKey === 'exited';

  const memMb = stats ? (stats.memory_usage / (1024 * 1024)).toFixed(0) : null;
  const memLimitMb = stats ? (stats.memory_limit / (1024 * 1024)).toFixed(0) : null;
  const cpu = stats?.cpu_percent?.toFixed(1);

  // 按時計費
  const cost = calcCost(container.uptime_seconds, hourlyRate);
  const hours = (container.uptime_seconds / 3600).toFixed(1);

  return (
    <div className="rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)]/80 p-4 transition-colors hover:border-[var(--console-line)]">
      {/* 头部：服务名 + 状态 */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-base">🐳</span>
          <div>
            <p className="text-sm font-medium text-[var(--console-ink)]">{container.service}</p>
            <p className="text-[11px] text-[var(--console-faint)]">{container.name}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* 按時計費標籤 */}
          {isReal && isRunning && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium console-status-amber">
              {formatRate(hourlyRate)} · {hours}h
            </span>
          )}
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${statusColor}`}>
            {container.status}
          </span>
          {isReal && (
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${healthColor}`}>
              {container.health}
            </span>
          )}
        </div>
      </div>

      {/* 资源使用 + 费用 */}
      {stats && !stats.error && (
        <div className="mb-3 grid grid-cols-4 gap-2 rounded-md bg-gray-950/60 px-3 py-2">
          <div className="text-center">
            <p className="text-[10px] uppercase text-[var(--console-faint)]">CPU</p>
            <p className="text-xs font-semibold text-[var(--console-ink)]">{cpu ?? '--'}%</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-[var(--console-faint)]">内存</p>
            <p className="text-xs font-semibold text-[var(--console-ink)]">
              {memMb ?? '--'}{memLimitMb ? ` / ${memLimitMb} MB` : ' MB'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-[var(--console-faint)]">网络</p>
            <p className="text-xs font-semibold text-[var(--console-ink)]">
              {stats ? `${((stats.network_rx + stats.network_tx) / (1024 * 1024)).toFixed(1)} MB` : '--'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-amber-400">费用</p>
            <p className="text-xs font-semibold console-status-amber">{formatCost(cost)}</p>
          </div>
        </div>
      )}

      {/* 无资源统计时仍显示费用行 */}
      {(!stats || stats.error) && isRunning && (
        <div className="mb-3 rounded-md bg-gray-950/60 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase text-[var(--console-faint)]">运行时长</span>
            <span className="text-xs text-[var(--console-sub)]">{hours} 小时</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span className="text-[10px] uppercase text-amber-400">累计费用</span>
            <span className="text-xs font-semibold console-status-amber">{formatCost(cost)}</span>
          </div>
        </div>
      )}

      {/* 端口 */}
      {container.ports.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {container.ports.map((p) => (
            <span key={p} className="rounded bg-[var(--console-dim)] px-2 py-0.5 text-[11px] text-[var(--console-faint)]">
              {p}
            </span>
          ))}
        </div>
      )}

      {/* 操作按钮 */}
      {isReal && (
        <div className="flex items-center gap-2 border-t border-[var(--console-line)] pt-3">
          <button
            onClick={onViewLogs}
            disabled={isBusy}
            className="rounded-md bg-[var(--console-dim)] px-2.5 py-1 text-[11px] text-[var(--console-faint)] transition-colors hover:bg-gray-700 hover:text-[var(--console-ink)] disabled:opacity-40"
          >
            📋 日志
          </button>

          {isRunning && (
            <>
              <button
                onClick={() => {
                  if (confirming === `restart-${container.service}`) {
                    onRestart();
                    setConfirming(null);
                  } else {
                    setConfirming(`restart-${container.service}`);
                  }
                }}
                disabled={isBusy}
                className={`rounded-md px-2.5 py-1 text-[11px] transition-colors disabled:opacity-40 ${
                  confirming === `restart-${container.service}`
                    ? 'bg-yellow-500/20 text-yellow-300'
                    : 'bg-[var(--console-dim)] text-[var(--console-faint)] hover:bg-yellow-500/10 hover:text-yellow-300'
                }`}
              >
                {confirming === `restart-${container.service}` ? '⚠ 确认重启?' : '🔄 重启'}
              </button>
              <button
                onClick={() => {
                  if (confirming === `stop-${container.service}`) {
                    onStop();
                    setConfirming(null);
                  } else {
                    setConfirming(`stop-${container.service}`);
                  }
                }}
                disabled={isBusy}
                className={`rounded-md px-2.5 py-1 text-[11px] transition-colors disabled:opacity-40 ${
                  confirming === `stop-${container.service}`
                    ? 'bg-red-500/20 console-status-danger'
                    : 'bg-[var(--console-dim)] text-[var(--console-faint)] hover:bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] hover:console-status-danger'
                }`}
              >
                {confirming === `stop-${container.service}` ? '⚠ 确认停止?' : '⏹ 停止'}
              </button>
            </>
          )}

          {isStopped && (
            <button
              onClick={() => {
                if (confirming === `start-${container.service}`) {
                  onStart();
                  setConfirming(null);
                } else {
                  setConfirming(`start-${container.service}`);
                }
              }}
              disabled={isBusy}
              className={`rounded-md px-2.5 py-1 text-[11px] transition-colors disabled:opacity-40 ${
                confirming === `start-${container.service}`
                  ? 'bg-green-500/20 console-status-green'
                  : 'bg-[var(--console-dim)] text-[var(--console-faint)] hover:bg-green-500/10 hover:console-status-green'
              }`}
            >
              {confirming === `start-${container.service}` ? '✓ 确认启动?' : '▶ 启动'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
