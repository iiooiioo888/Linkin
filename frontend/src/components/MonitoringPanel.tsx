/**
 * MonitoringPanel — 資源監控圖表面板。
 *
 * 顯示 CPU / 記憶體 / 網路使用量折線圖，
 * 支援 1h / 6h / 24h 時間範圍切換。
 * 圖表走 Apache ECharts（Apache-2.0，無需授權）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchCloudMonitoring } from '../api/client';
import { useFixedPages, usePagination } from '../lib/pagination';
import type { CloudMonitoring } from '../types';
import LcLineChart from './charts/LcLineChart';
import { ConsolePageFrame, ConsolePagination } from './ui/ConsolePagination';

const RANGE_OPTIONS = [
  { value: '1h', label: '1 小時' },
  { value: '6h', label: '6 小時' },
  { value: '24h', label: '24 小時' },
] as const;

const SERVICE_COLORS: Record<string, string> = {
  backend: '#60a5fa',
  frontend: '#34d399',
  opc: '#f472b6',
  redis: '#fbbf24',
  chroma: '#a78bfa',
};

function getColor(svc: string): string {
  return SERVICE_COLORS[svc] ?? '#9ca3af';
}

function MiniLineChart({
  points,
  maxY,
  height,
  color,
  label,
  unit,
}: {
  points: number[];
  maxY: number;
  height: number;
  color: string;
  label: string;
  unit: string;
}) {
  if (points.length < 2) {
    return (
      <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-3">
        <p className="mb-1 text-[10px] uppercase text-gray-500">{label}</p>
        <p className="text-xs text-gray-600">數據不足</p>
      </div>
    );
  }

  const latest = points[points.length - 1];

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-3">
      <div className="mb-1 flex items-center justify-between">
        <p className="text-[10px] uppercase text-gray-500">{label}</p>
        <p className="text-xs font-semibold" style={{ color }}>
          {latest.toFixed(1)}{unit}
        </p>
      </div>
      <LcLineChart
        height={height}
        yMax={maxY || 1}
        series={[
          {
            id: label,
            color,
            points: points.map((y, x) => ({ x, y })),
          },
        ]}
      />
    </div>
  );
}

export default function MonitoringPanel({ embedded = false }: { embedded?: boolean }) {
  const [monitoring, setMonitoring] = useState<CloudMonitoring | null>(null);
  const [range, setRange] = useState<string>('1h');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchCloudMonitoring(range);
      setMonitoring(data);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 30000);
    return () => clearInterval(timer);
  }, [refresh]);

  // 提取服務列表與各類數據
  const { services, cpuSeries, memSeries, netRxSeries } = useMemo(() => {
    if (!monitoring?.points?.length) {
      return { services: [] as string[], cpuSeries: {} as Record<string, number[]>, memSeries: {} as Record<string, number[]>, netRxSeries: {} as Record<string, number[]> };
    }

    const svcSet = new Set<string>();
    for (const p of monitoring.points) {
      for (const svc of Object.keys(p.services)) {
        svcSet.add(svc);
      }
    }
    const svcList = [...svcSet].sort();

    const cpu: Record<string, number[]> = {};
    const mem: Record<string, number[]> = {};
    const net: Record<string, number[]> = {};

    for (const svc of svcList) {
      cpu[svc] = [];
      mem[svc] = [];
      net[svc] = [];
    }

    for (const p of monitoring.points) {
      for (const svc of svcList) {
        const s = p.services[svc];
        cpu[svc].push(s?.cpu ?? 0);
        mem[svc].push(s?.mem_mb ?? 0);
        net[svc].push(s?.net_rx_mb ?? 0);
      }
    }

    return { services: svcList, cpuSeries: cpu, memSeries: mem, netRxSeries: net };
  }, [monitoring]);

  // 計算各圖表的最大值
  const maxCpu = useMemo(() => {
    let m = 0;
    for (const arr of Object.values(cpuSeries)) {
      for (const v of arr) if (v > m) m = v;
    }
    return Math.max(m, 10);
  }, [cpuSeries]);

  const maxMem = useMemo(() => {
    let m = 0;
    for (const arr of Object.values(memSeries)) {
      for (const v of arr) if (v > m) m = v;
    }
    return Math.max(m, 10);
  }, [memSeries]);

  const maxNet = useMemo(() => {
    let m = 0;
    for (const arr of Object.values(netRxSeries)) {
      for (const v of arr) if (v > m) m = v;
    }
    return Math.max(m, 1);
  }, [netRxSeries]);

  const chartPager = useFixedPages(3);
  const svcPager = usePagination(services, embedded ? 2 : services.length || 1);
  const showChart = (n: number) => !embedded || chartPager.page === n;
  const visibleServices = embedded ? svcPager.slice : services;

  const body = (
    <div className={embedded ? 'space-y-3' : 'flex-1 space-y-4 overflow-auto p-4'}>
      {/* 時間範圍選擇器 */}
      <div className="flex items-center justify-between">
        {!embedded ? <h3 className="text-sm font-medium text-gray-200">資源監控</h3> : <span />}
        <div className="flex items-center gap-1 rounded-lg bg-gray-900 p-0.5">
          {RANGE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setRange(opt.value)}
              className={`rounded-md px-3 py-1 text-[11px] transition-colors ${
                range === opt.value
                  ? 'bg-blue-500/20 console-status-blue'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {opt.label}
            </button>
          ))}
          <button
            onClick={() => void refresh()}
            disabled={loading}
            className="ml-2 rounded-md px-2 py-1 text-[11px] text-gray-500 hover:text-gray-300 disabled:opacity-40"
          >
            {loading ? '⏳' : '🔄'}
          </button>
        </div>
      </div>

      {/* 錯誤提示 */}
      {error && (
        <div className="rounded-lg bg-red-500/15 px-4 py-2 text-sm console-status-danger">
          ⚠ {error}
        </div>
      )}

      {/* 無數據：仍畫出預期服務卡，避免整頁空白 */}
      {!loading && services.length === 0 && (
        <div className="rounded-lg border border-gray-800 bg-gray-900/80 p-4">
          <p className="text-sm text-gray-300">暫無監控採樣</p>
          <p className="mt-1 text-xs text-gray-500">後台每 60 秒採集一次 Docker stats，請稍候或確認 docker.sock。</p>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {['backend', 'frontend', 'opc', 'redis', 'chroma'].map((svc) => (
              <div key={svc} className="rounded-md border border-gray-800 bg-gray-950/40 p-3">
                <p className="text-[10px] uppercase text-gray-500">{svc}</p>
                <div className="mt-2 h-8 rounded bg-gray-800/80" />
                <p className="mt-1 text-[11px] text-gray-600">CPU — · MEM —</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* CPU 圖表 */}
      {services.length > 0 && showChart(1) && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase text-gray-500">CPU 使用率 (%)</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {visibleServices.map((svc) => (
              <MiniLineChart
                key={`cpu-${svc}`}
                points={cpuSeries[svc]}
                maxY={maxCpu}
                height={64}
                color={getColor(svc)}
                label={svc}
                unit="%"
              />
            ))}
          </div>
          {embedded ? (
            <ConsolePagination page={svcPager.page} totalPages={svcPager.pages} onPageChange={svcPager.setPage} className="!border-0" />
          ) : null}
        </div>
      )}

      {/* 記憶體圖表 */}
      {services.length > 0 && showChart(2) && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase text-gray-500">記憶體 (MB)</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {visibleServices.map((svc) => (
              <MiniLineChart
                key={`mem-${svc}`}
                points={memSeries[svc]}
                maxY={maxMem}
                height={64}
                color={getColor(svc)}
                label={svc}
                unit=" MB"
              />
            ))}
          </div>
          {embedded ? (
            <ConsolePagination page={svcPager.page} totalPages={svcPager.pages} onPageChange={svcPager.setPage} className="!border-0" />
          ) : null}
        </div>
      )}

      {/* 網路圖表 */}
      {services.length > 0 && showChart(3) && (
        <div>
          <p className="mb-2 text-[11px] font-semibold uppercase text-gray-500">網路接收 (MB)</p>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {visibleServices.map((svc) => (
              <MiniLineChart
                key={`net-${svc}`}
                points={netRxSeries[svc]}
                maxY={maxNet}
                height={64}
                color={getColor(svc)}
                label={svc}
                unit=" MB"
              />
            ))}
          </div>
          {embedded ? (
            <ConsolePagination page={svcPager.page} totalPages={svcPager.pages} onPageChange={svcPager.setPage} className="!border-0" />
          ) : null}
        </div>
      )}
    </div>
  );

  if (embedded) {
    return (
      <ConsolePageFrame
        page={chartPager.page}
        totalPages={chartPager.pages}
        onPageChange={(p) => {
          chartPager.setPage(p);
          svcPager.reset();
        }}
      >
        {body}
      </ConsolePageFrame>
    );
  }
  return body;
}