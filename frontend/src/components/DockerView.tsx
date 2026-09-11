/**
 * DockerView — Docker 容器管理 GUI。
 *
 * 提供容器状态监控、资源统计、健康检查、日志查看与启停控制。
 * 每 8 秒自动刷新状态，支持手动刷新。
 * 采用阿里雲式按時計費：每個容器顯示小時費率與累計費用。
 *
 * 安全控制：仅 Manager/DevOps 可执行写操作（重启/停止/启动）。
 * 前端层面做二次确认，后端由 DockerManager 安全护栏兜底。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { DockerBudget, DockerContainer, DockerContainerStats, DockerHealth, DockerStatus } from '../types';
import {
  fetchDockerBudget,
  fetchDockerLogs,
  fetchDockerStats,
  fetchDockerStatus,
  restartDockerService,
  startDockerService,
  stopDockerService,
} from '../api/client';

// ═══════════════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════════════

const REFRESH_INTERVAL = 8000; // 8 秒自动刷新

const STATUS_COLORS: Record<string, string> = {
  running: 'bg-green-500/20 text-green-300',
  exited: 'bg-red-500/20 text-red-300',
  restarting: 'bg-yellow-500/20 text-yellow-300',
  paused: 'bg-gray-500/20 text-gray-400',
  removing: 'bg-red-500/20 text-red-300',
};

const HEALTH_COLORS: Record<string, string> = {
  healthy: 'bg-green-500/20 text-green-300',
  unhealthy: 'bg-red-500/20 text-red-300',
  starting: 'bg-yellow-500/20 text-yellow-300',
  unknown: 'bg-gray-500/20 text-gray-400',
};

function statusLabel(status: string): string {
  if (status.startsWith('Up')) return 'running';
  if (status.startsWith('Exited')) return 'exited';
  if (status.startsWith('Restarting')) return 'restarting';
  return status.toLowerCase();
}

// ═══════════════════════════════════════════════════════════
// 子组件
// ═══════════════════════════════════════════════════════════

function formatRate(rate: number): string {
  return `$${rate.toFixed(3)}/h`;
}

function calcCost(uptimeSeconds: number, rate: number): number {
  return (uptimeSeconds / 3600) * rate;
}

function formatCost(amount: number): string {
  if (amount < 0.01) return `$${amount.toFixed(4)}`;
  if (amount < 1) return `$${amount.toFixed(3)}`;
  return `$${amount.toFixed(2)}`;
}

/** 容器卡片 */
function ContainerCard({
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
  const statusColor = STATUS_COLORS[statusKey] || 'bg-gray-500/20 text-gray-400';
  const healthColor = HEALTH_COLORS[container.health] || 'bg-gray-500/20 text-gray-400';

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
    <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-4 transition-colors hover:border-gray-700">
      {/* 头部：服务名 + 状态 */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="text-base">🐳</span>
          <div>
            <p className="text-sm font-medium text-gray-200">{container.service}</p>
            <p className="text-[11px] text-gray-500">{container.name}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* 按時計費標籤 */}
          {isReal && isRunning && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300">
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
            <p className="text-[10px] uppercase text-gray-500">CPU</p>
            <p className="text-xs font-semibold text-gray-200">{cpu ?? '--'}%</p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-gray-500">内存</p>
            <p className="text-xs font-semibold text-gray-200">
              {memMb ?? '--'}{memLimitMb ? ` / ${memLimitMb} MB` : ' MB'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-gray-500">网络</p>
            <p className="text-xs font-semibold text-gray-200">
              {stats ? `${((stats.network_rx + stats.network_tx) / (1024 * 1024)).toFixed(1)} MB` : '--'}
            </p>
          </div>
          <div className="text-center">
            <p className="text-[10px] uppercase text-amber-400">费用</p>
            <p className="text-xs font-semibold text-amber-300">{formatCost(cost)}</p>
          </div>
        </div>
      )}

      {/* 无资源统计时仍显示费用行 */}
      {(!stats || stats.error) && isRunning && (
        <div className="mb-3 rounded-md bg-gray-950/60 px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] uppercase text-gray-500">运行时长</span>
            <span className="text-xs text-gray-300">{hours} 小时</span>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span className="text-[10px] uppercase text-amber-400">累计费用</span>
            <span className="text-xs font-semibold text-amber-300">{formatCost(cost)}</span>
          </div>
        </div>
      )}

      {/* 端口 */}
      {container.ports.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {container.ports.map((p) => (
            <span key={p} className="rounded bg-gray-800 px-2 py-0.5 text-[11px] text-gray-400">
              {p}
            </span>
          ))}
        </div>
      )}

      {/* 操作按钮 */}
      {isReal && (
        <div className="flex items-center gap-2 border-t border-gray-800 pt-3">
          <button
            onClick={onViewLogs}
            disabled={isBusy}
            className="rounded-md bg-gray-800 px-2.5 py-1 text-[11px] text-gray-400 transition-colors hover:bg-gray-700 hover:text-gray-200 disabled:opacity-40"
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
                    : 'bg-gray-800 text-gray-400 hover:bg-yellow-500/10 hover:text-yellow-300'
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
                    ? 'bg-red-500/20 text-red-300'
                    : 'bg-gray-800 text-gray-400 hover:bg-red-500/10 hover:text-red-300'
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
                  ? 'bg-green-500/20 text-green-300'
                  : 'bg-gray-800 text-gray-400 hover:bg-green-500/10 hover:text-green-300'
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

/** 健康检查摘要栏 */
function HealthBar({ health }: { health: DockerHealth }) {
  const total = Object.keys(health.services).length;
  const healthy = Object.values(health.services).filter((s) => s.healthy).length;
  const unhealthy = total - healthy;

  return (
    <div className="flex items-center gap-4 rounded-lg border border-gray-800 bg-gray-900/80 px-4 py-2.5">
      <span className="text-xs font-medium text-gray-400">健康检查</span>
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs">
          <span className="inline-block h-2 w-2 rounded-full bg-green-400" />
          <span className="text-green-300">{healthy} 健康</span>
        </span>
        {unhealthy > 0 && (
          <span className="flex items-center gap-1.5 text-xs">
            <span className="inline-block h-2 w-2 rounded-full bg-red-400" />
            <span className="text-red-300">{unhealthy} 异常</span>
          </span>
        )}
        <span className="text-xs text-gray-500">共 {total} 服务</span>
      </div>
      <span
        className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${
          health.all_healthy
            ? 'bg-green-500/20 text-green-300'
            : 'bg-red-500/20 text-red-300'
        }`}
      >
        {health.all_healthy ? '全部健康' : '存在异常'}
      </span>
    </div>
  );
}

/** 日志查看弹窗 */
function LogModal({
  service,
  logs,
  loading,
  onClose,
  onRefresh,
  tail,
  onTailChange,
}: {
  service: string;
  logs: string;
  loading: boolean;
  onClose: () => void;
  onRefresh: () => void;
  tail: number;
  onTailChange: (t: number) => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-gray-700 bg-gray-900 shadow-2xl">
        {/* 头部 */}
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-base">📋</span>
            <span className="text-sm font-medium text-gray-200">{service} 日志</span>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={tail}
              onChange={(e) => onTailChange(Number(e.target.value))}
              className="rounded-md border border-gray-700 bg-gray-800 px-2 py-1 text-[11px] text-gray-300"
            >
              <option value={50}>最近 50 行</option>
              <option value={100}>最近 100 行</option>
              <option value={200}>最近 200 行</option>
              <option value={500}>最近 500 行</option>
            </select>
            <button
              onClick={onRefresh}
              disabled={loading}
              className="rounded-md bg-gray-800 px-2.5 py-1 text-[11px] text-gray-400 transition-colors hover:bg-gray-700 disabled:opacity-40"
            >
              {loading ? '加载中...' : '🔄 刷新'}
            </button>
            <button
              onClick={onClose}
              className="rounded-md px-2 py-1 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
            >
              ✕
            </button>
          </div>
        </div>

        {/* 日志内容 */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <span className="text-sm text-gray-500">加载中...</span>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed text-gray-400">
              {logs || '暂无日志'}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// 主组件
// ═══════════════════════════════════════════════════════════

export default function DockerView({ embedded = false }: { embedded?: boolean }) {
  const [status, setStatus] = useState<DockerStatus | null>(null);
  const [stats, setStats] = useState<Record<string, DockerContainerStats> | null>(null);
  const [budget, setBudget] = useState<DockerBudget | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyService, setBusyService] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ text: string; ok: boolean } | null>(null);

  // 日志弹窗
  const [logModal, setLogModal] = useState<{ service: string } | null>(null);
  const [logContent, setLogContent] = useState('');
  const [logLoading, setLogLoading] = useState(false);
  const [logTail, setLogTail] = useState(100);

  // ── 数据加载 ──
  const refresh = useCallback(async () => {
    try {
      const [statusData, statsData, budgetData] = await Promise.all([
        fetchDockerStatus(),
        fetchDockerStats().catch(() => ({ stats: {} })),
        fetchDockerBudget().catch(() => null),
      ]);
      setStatus(statusData);
      setStats(statsData.stats);
      setBudget(budgetData);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // 自动刷新
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), REFRESH_INTERVAL);
    return () => clearInterval(timer);
  }, [refresh]);

  // 操作消息自动消失
  useEffect(() => {
    if (!actionMessage) return;
    const timer = setTimeout(() => setActionMessage(null), 4000);
    return () => clearTimeout(timer);
  }, [actionMessage]);

  // ── 操作处理 ──
  const handleAction = useCallback(
    async (service: string, action: 'restart' | 'stop' | 'start') => {
      setBusyService(service);
      try {
        let result;
        if (action === 'restart') result = await restartDockerService(service);
        else if (action === 'stop') result = await stopDockerService(service);
        else result = await startDockerService(service);

        setActionMessage({
          text: result.message,
          ok: result.success,
        });

        // 立即刷新
        await refresh();
      } catch (err) {
        setActionMessage({
          text: (err as Error).message,
          ok: false,
        });
      } finally {
        setBusyService(null);
      }
    },
    [refresh],
  );

  const handleViewLogs = useCallback(
    async (service: string) => {
      setLogModal({ service });
      setLogLoading(true);
      try {
        const data = await fetchDockerLogs(service, logTail);
        setLogContent(data.logs);
      } catch (err) {
        setLogContent(`加载失败：${(err as Error).message}`);
      } finally {
        setLogLoading(false);
      }
    },
    [logTail],
  );

  const handleRefreshLogs = useCallback(async () => {
    if (!logModal) return;
    setLogLoading(true);
    try {
      const data = await fetchDockerLogs(logModal.service, logTail);
      setLogContent(data.logs);
    } catch (err) {
      setLogContent(`加载失败：${(err as Error).message}`);
    } finally {
      setLogLoading(false);
    }
  }, [logModal, logTail]);

  // ── 排序容器 ──
  const sortedContainers = useMemo(() => {
    if (!status?.containers) return [];
    const order = ['backend', 'frontend', 'opc', 'redis', 'chroma'];
    return [...status.containers].sort((a, b) => {
      const ai = order.indexOf(a.service);
      const bi = order.indexOf(b.service);
      if (ai === -1 && bi === -1) return a.service.localeCompare(b.service);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
  }, [status]);

  // ── 渲染 ──
  if (loading && !status) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <span className="animate-spin text-3xl">🐳</span>
          <p className="text-sm text-gray-500">加载 Docker 容器状态...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={embedded ? 'space-y-3' : 'flex flex-1 flex-col overflow-auto'}>
      {/* 操作消息横幅 */}
      {actionMessage && (
        <div
          className={`${embedded ? '' : 'mx-4 mt-3 '}rounded-lg px-4 py-2 text-sm ${
            actionMessage.ok
              ? 'bg-green-500/15 text-green-300'
              : 'bg-red-500/15 text-red-300'
          }`}
        >
          {actionMessage.text}
        </div>
      )}

      {/* 错误横幅 */}
      {error && (
        <div className="mx-4 mt-3 rounded-lg bg-red-500/15 px-4 py-2 text-sm text-red-300">
          ⚠ {error}
          <button
            onClick={() => void refresh()}
            className="ml-3 underline hover:text-red-200"
          >
            重试
          </button>
        </div>
      )}

      {/* 页面内容 */}
      <div className="flex-1 space-y-4 p-4">
        {/* 标题栏 */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-200">Docker 容器管理</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {status?.available
                ? `监控 ${sortedContainers.length} 个容器 · 自动刷新`
                : 'Docker 不可用 — 请确认后端已挂载 docker.sock'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-gray-500">
              {loading ? '刷新中...' : '每 8 秒自动刷新'}
            </span>
            <button
              onClick={() => void refresh()}
              disabled={loading}
              className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-300 transition-colors hover:bg-gray-700 disabled:opacity-40"
            >
              {loading ? '⏳' : '🔄'} 手动刷新
            </button>
          </div>
        </div>

        {/* 健康检查摘要 */}
        {status?.health && !status.health._error && (
          <HealthBar health={status.health} />
        )}

        {/* 按時計費費率表 + 總費用 */}
        {status?.hourly_rates && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5">
              <span className="text-[11px] font-semibold text-amber-300">💰 按時計費</span>
              {Object.entries(status.hourly_rates).map(([svc, rate]) => (
                <span key={svc} className="text-[11px] text-gray-500">
                  {svc} {formatRate(rate)}
                </span>
              ))}
              <span className="ml-auto text-[11px] font-semibold text-amber-300">
                累计 {formatCost(sortedContainers.reduce((sum, c) => {
                  const rate = status.hourly_rates[c.service] ?? 0.01;
                  return sum + calcCost(c.uptime_seconds, rate);
                }, 0))}
              </span>
            </div>
          </div>
        )}

        {/* 公司預算與優化建議 */}
        {budget?.company_budget && (
          <div className="apple-card apple-card--tight !p-0 p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                公司預算
              </p>
              <span className="font-mono text-xs text-amber-300">
                Docker {formatCost(budget.total_docker_cost)} · 合計{' '}
                {formatCost(budget.company_budget.total_spent)} · 壓力{' '}
                {Math.round((budget.company_budget.budget_pressure ?? 0) * 100)}%
              </span>
            </div>
            {(budget.company_budget.optimization_suggestions?.length ?? 0) === 0 ? (
              <p className="text-[11px] text-gray-500">目前無需自動優化。</p>
            ) : (
              <div className="space-y-1">
                {budget.company_budget.optimization_suggestions.map((s) => (
                  <div
                    key={`${s.service}-${s.action}`}
                    className="flex items-center justify-between rounded-md bg-gray-950/50 px-2 py-1.5 text-[11px]"
                  >
                    <span className="text-gray-300">
                      {s.priority} · {s.service} {s.action}
                    </span>
                    <span className="text-gray-500">{s.reason}</span>
                    <span className="font-mono text-green-300">
                      -{formatCost(s.estimated_saving_per_hour)}/h
                    </span>
                  </div>
                ))}
              </div>
            )}
            {(budget.company_budget.auto_optimized?.stopped?.length ?? 0) > 0 && (
              <p className="mt-2 text-[11px] text-amber-300">
                已自動停止：{budget.company_budget.auto_optimized.stopped.join(', ')}
              </p>
            )}
          </div>
        )}

        {/* 容器卡片网格 */}
        <div className="grid gap-3 sm:grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
          {sortedContainers.map((c) => (
            <ContainerCard
              key={c.name}
              container={c}
              stats={stats?.[c.service]}
              isBusy={busyService === c.service}
              hourlyRate={status?.hourly_rates?.[c.service] ?? 0.01}
              onRestart={() => void handleAction(c.service, 'restart')}
              onStop={() => void handleAction(c.service, 'stop')}
              onStart={() => void handleAction(c.service, 'start')}
              onViewLogs={() => void handleViewLogs(c.service)}
            />
          ))}
        </div>

        {sortedContainers.length === 0 && (
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 p-4">
            <p className="text-sm text-gray-300">未發現 EvoLoop 容器</p>
            <p className="mt-1 text-xs text-gray-500">
              請確認 Docker Compose 已啟動且後端已掛載 docker.sock
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {['backend', 'frontend', 'opc', 'redis', 'chroma'].map((svc) => (
                <div key={svc} className="rounded-md border border-dashed border-gray-700 px-3 py-3">
                  <p className="text-xs font-medium text-gray-400">{svc}</p>
                  <p className="mt-1 text-[11px] text-gray-600">待命</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 日志弹窗 */}
      {logModal && (
        <LogModal
          service={logModal.service}
          logs={logContent}
          loading={logLoading}
          onClose={() => setLogModal(null)}
          onRefresh={() => void handleRefreshLogs()}
          tail={logTail}
          onTailChange={(t) => {
            setLogTail(t);
            // 触发重新加载
            setLogModal((prev) => (prev ? { ...prev } : null));
          }}
        />
      )}
    </div>
  );
}