/**
 * Docker 容器管理主體：資料載入／自動刷新／啟停操作／日誌彈窗與分頁組裝。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useFixedPages, usePagination } from '../../lib/pagination';
import type { DockerBudget, DockerContainerStats, DockerStatus } from '../../types';
import { ConsolePageFrame, ConsolePagination } from '../ui/ConsolePagination';
import {
  fetchDockerBudget,
  fetchDockerLogs,
  fetchDockerStats,
  fetchDockerStatus,
  restartDockerService,
  startDockerService,
  stopDockerService,
} from '../../api/client';
import { ContainerCard } from './ContainerCard';
import { HealthBar } from './HealthBar';
import { LogModal } from './LogModal';
import { REFRESH_INTERVAL, calcCost, formatCost, formatRate } from './shared';

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

  const embeddedPager = useFixedPages(2);
  const containerPager = usePagination(sortedContainers, embedded ? 2 : sortedContainers.length || 1);

  // ── 渲染 ──
  if (loading && !status) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <span className="animate-spin text-3xl">🐳</span>
          <p className="text-sm text-[var(--console-faint)]">加载 Docker 容器状态...</p>
        </div>
      </div>
    );
  }

  const inner = (
    <div className={embedded ? 'space-y-3' : 'flex flex-1 flex-col overflow-auto'}>
      {/* 操作消息横幅 */}
      {actionMessage && (
        <div
          className={`${embedded ? '' : 'mx-4 mt-3 '}rounded-lg px-4 py-2 text-sm ${
            actionMessage.ok
              ? 'bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] console-status-green'
              : 'bg-red-500/15 console-status-danger'
          }`}
        >
          {actionMessage.text}
        </div>
      )}

      {/* 错误横幅 */}
      {error && (
        <div className="mx-4 mt-3 rounded-lg bg-red-500/15 px-4 py-2 text-sm console-status-danger">
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
      <div className={`flex-1 space-y-4 ${embedded ? '' : 'p-4'}`}>
        {(!embedded || embeddedPager.page === 1) && (
        <>
        {/* 标题栏 */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-[var(--console-ink)]">Docker 容器管理</h2>
            <p className="mt-0.5 text-xs text-[var(--console-faint)]">
              {status?.available
                ? `监控 ${sortedContainers.length} 个容器 · 自动刷新`
                : 'Docker 不可用 — 请确认后端已挂载 docker.sock'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-[var(--console-faint)]">
              {loading ? '刷新中...' : '每 8 秒自动刷新'}
            </span>
            <button
              onClick={() => void refresh()}
              disabled={loading}
              className="rounded-lg border border-[var(--console-line)] bg-[var(--console-dim)] px-3 py-1.5 text-xs text-[var(--console-sub)] transition-colors hover:bg-gray-700 disabled:opacity-40"
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
              <span className="text-[11px] font-semibold console-status-amber">💰 按時計費</span>
              {Object.entries(status.hourly_rates).map(([svc, rate]) => (
                <span key={svc} className="text-[11px] text-[var(--console-faint)]">
                  {svc} {formatRate(rate)}
                </span>
              ))}
              <span className="ml-auto text-[11px] font-semibold console-status-amber">
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
              <p className="text-[11px] font-semibold text-[var(--console-faint)]">
                公司預算
              </p>
              <span className="font-mono text-xs console-status-amber">
                Docker {formatCost(budget.total_docker_cost)} · 合計{' '}
                {formatCost(budget.company_budget.total_spent)} · 壓力{' '}
                {Math.round((budget.company_budget.budget_pressure ?? 0) * 100)}%
              </span>
            </div>
            {(budget.company_budget.optimization_suggestions?.length ?? 0) === 0 ? (
              <p className="text-[11px] text-[var(--console-faint)]">目前無需自動優化。</p>
            ) : (
              <div className="space-y-1">
                {budget.company_budget.optimization_suggestions.map((s) => (
                  <div
                    key={`${s.service}-${s.action}`}
                    className="flex items-center justify-between rounded-md bg-gray-950/50 px-2 py-1.5 text-[11px]"
                  >
                    <span className="text-[var(--console-sub)]">
                      {s.priority} · {s.service} {s.action}
                    </span>
                    <span className="text-[var(--console-faint)]">{s.reason}</span>
                    <span className="font-mono console-status-green">
                      -{formatCost(s.estimated_saving_per_hour)}/h
                    </span>
                  </div>
                ))}
              </div>
            )}
            {(budget.company_budget.auto_optimized?.stopped?.length ?? 0) > 0 && (
              <p className="mt-2 text-[11px] console-status-amber">
                已自動停止：{budget.company_budget.auto_optimized.stopped.join(', ')}
              </p>
            )}
          </div>
        )}
        </>
        )}

        {(!embedded || embeddedPager.page === 2) && (
        <>
        {/* 容器卡片网格 */}
        <div className="grid gap-3 sm:grid-cols-1 lg:grid-cols-2">
          {(embedded ? containerPager.slice : sortedContainers).map((c) => (
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
          <div className="rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)]/60 p-4">
            <p className="text-sm text-[var(--console-sub)]">未發現 Linkin 容器</p>
            <p className="mt-1 text-xs text-[var(--console-faint)]">
              請確認 Docker Compose 已啟動且後端已掛載 docker.sock
            </p>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {['backend', 'frontend', 'opc', 'redis', 'chroma'].map((svc) => (
                <div key={svc} className="rounded-md border border-dashed border-[var(--console-line)] px-3 py-3">
                  <p className="text-xs font-medium text-[var(--console-faint)]">{svc}</p>
                  <p className="mt-1 text-[11px] text-gray-600">待命</p>
                </div>
              ))}
            </div>
          </div>
        )}
        {embedded ? (
          <ConsolePagination page={containerPager.page} totalPages={containerPager.pages} onPageChange={containerPager.setPage} className="!border-0" />
        ) : null}
        </>
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

  if (embedded) {
    return (
      <ConsolePageFrame
        page={embeddedPager.page}
        totalPages={embeddedPager.pages}
        onPageChange={(p) => {
          embeddedPager.setPage(p);
          if (p === 2) containerPager.reset();
        }}
      >
        {inner}
      </ConsolePageFrame>
    );
  }
  return inner;
}
