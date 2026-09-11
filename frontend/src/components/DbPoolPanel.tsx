/**
 * DbPoolPanel — 數據庫連接池管理 UI。
 * 
 * 提供連接池狀態監控、連接管理、健康檢查等功能。
 */
import { useEffect, useState } from 'react';
import {
  fetchDbPoolStats,
  refreshDbPool,
  closeDbConnection,
  runDbHealthCheck,
  type DbPoolStats,
} from '../api/client';
import { usePagination } from '../lib/pagination';
import { ConsolePagination } from './ui/ConsolePagination';
import { PanelScroll, PanelShell, SectionHeader, consoleLayout } from './ui/ConsoleLayout';

export default function DbPoolPanel({ embedded = false }: { embedded?: boolean }) {
  const [stats, setStats] = useState<DbPoolStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<{ healthy: boolean; details: string } | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const loadStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDbPoolStats();
      setStats(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const data = await refreshDbPool(2);
      setStats(data);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRefreshing(false);
    }
  };

  const handleCloseConnection = async (connectionId: string) => {
    if (!confirm(`確定要關閉連接 ${connectionId}？`)) return;
    try {
      await closeDbConnection(connectionId);
      await loadStats();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleHealthCheck = async () => {
    try {
      const result = await runDbHealthCheck();
      setHealthStatus(result);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  useEffect(() => {
    void loadStats();
    // 每 5 秒自動刷新
    const interval = setInterval(loadStats, 5000);
    return () => clearInterval(interval);
  }, []);

  const connPager = usePagination(stats?.connections ?? [], embedded ? 5 : (stats?.connections?.length ?? 0) || 1);

  const body = (
      <div className="flex flex-col gap-3">
        {error && (
          <div className="rounded-md border border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-3 py-2 text-xs console-status-danger">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 text-[10px] underline hover:text-red-200"
            >
              關閉
            </button>
          </div>
        )}

        {healthStatus && (
          <div
            className={`rounded-md border px-3 py-2 text-xs ${
              healthStatus.healthy
                ? 'border-green-500/30 bg-green-500/10 console-status-green'
                : 'border-amber-500/30 bg-amber-500/10 console-status-amber'
            }`}
          >
            <span className="font-medium">
              {healthStatus.healthy ? '✓ 健康檢查通過' : '⚠ 健康檢查失敗'}
            </span>
            <span className="ml-2">{healthStatus.details}</span>
            <button
              onClick={() => setHealthStatus(null)}
              className="ml-2 text-[10px] underline hover:text-current"
            >
              關閉
            </button>
          </div>
        )}

        {/* 總覽卡片 */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard label="連接池大小" value={stats?.pool_size ?? 0} />
          <StatCard label="活躍連接" value={stats?.active_connections ?? 0} />
          <StatCard label="空閒連接" value={stats?.idle_connections ?? 0} />
          <StatCard label="總查詢數" value={stats?.total_queries ?? 0} />
          <StatCard label="平均延遲" value={`${stats?.avg_query_latency_ms ?? 0} ms`} />
        </div>

        {/* 操作按鈕 */}
        <div className="flex gap-2">
          <button
            onClick={loadStats}
            disabled={loading}
            className="rounded-md bg-[var(--console-blue)] px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            {loading ? '載入中...' : '🔄 刷新統計'}
          </button>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="rounded-md bg-[#34C759] px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            {refreshing ? '處理中...' : '♻️ 刷新連接池'}
          </button>
          <button
            onClick={handleHealthCheck}
            className="rounded-md bg-[#5856D6] px-3 py-2 text-xs font-medium text-white"
          >
            🏥 健康檢查
          </button>
        </div>

        {/* 連接列表 */}
        {stats && stats.connections.length > 0 && (
          <div className="flex-1 overflow-hidden">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-[var(--console-faint)]">
              連接詳情
            </h2>
            <div className="rounded-lg border border-white/[0.08] bg-[var(--console-card)]">
              <table className="w-full text-left text-[11px]">
                <thead className="sticky top-0 bg-[var(--console-card)]">
                  <tr>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">ID</th>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">數據庫路徑</th>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">狀態</th>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">查詢數</th>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">平均延遲</th>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">最後使用</th>
                    <th className="px-3 py-2 font-medium text-[var(--console-sub)]">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {(embedded ? connPager.slice : stats.connections).map((conn) => (
                    <tr
                      key={conn.id}
                      className="border-t border-white/[0.08] hover:bg-[var(--console-card)]"
                    >
                      <td className="px-3 py-2 font-mono console-status-blue">{conn.id}</td>
                      <td className="max-w-[200px] truncate px-3 py-2 text-[#d0d6e0]">
                        {conn.db_path}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] ${
                            conn.is_active
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-red-500/20 text-red-400'
                          }`}
                        >
                          {conn.is_active ? '● 活躍' : '○ 已關閉'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-[#d0d6e0]">{conn.query_count}</td>
                      <td className="px-3 py-2 text-[#d0d6e0]">{conn.avg_latency_ms} ms</td>
                      <td className="max-w-[150px] truncate px-3 py-2 text-[var(--console-sub)]">
                        {formatTime(conn.last_used_at)}
                      </td>
                      <td className="px-3 py-2">
                        <button
                          onClick={() => handleCloseConnection(conn.id)}
                          disabled={!conn.is_active}
                          className="rounded bg-red-500/20 px-2 py-1 text-[10px] text-red-400 hover:bg-red-500/30 disabled:opacity-50"
                        >
                          關閉
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {embedded ? (
              <ConsolePagination page={connPager.page} totalPages={connPager.pages} onPageChange={connPager.setPage} className="!border-0" />
            ) : null}
          </div>
        )}

        {stats && stats.connections.length === 0 && (
          <div className="flex flex-1 items-center justify-center text-xs text-[var(--console-faint)]">
            暫無連接記錄
          </div>
        )}
      </div>
  );

  if (embedded) return body;
  return (
    <PanelShell scroll={false}>
      <div className="shrink-0 border-b border-white/[0.08] px-6 py-4">
        <SectionHeader
          title="🗄️ 數據庫連接池管理"
          description="監控 SQLite 連接池狀態、管理連接、執行健康檢查"
        />
      </div>
      <PanelScroll className="flex flex-col gap-4">{body}</PanelScroll>
    </PanelShell>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className={consoleLayout.kpiCard}>
      <div className="text-[10px] uppercase tracking-wider text-[var(--console-faint)]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-[var(--console-ink)]">{value}</div>
    </div>
  );
}

function formatTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    return date.toLocaleString('zh-TW', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return isoString;
  }
}
