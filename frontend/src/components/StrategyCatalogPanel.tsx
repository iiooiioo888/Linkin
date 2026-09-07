/**
 * stock-quant 策略庫 — 分類樹，勾選可回測項交給角色 tool_call；右側顯示工作流與回測曲線。
 */
import { useEffect, useMemo, useState } from 'react';
import {
  labArchifyStrategy,
  labQuantPreview,
  labQuantStrategies,
  type QuantStrategyGroup,
  type QuantStrategyItem,
  type QuantStrategyPreview,
} from '../api/client';
import ArchifyViewer from './ArchifyViewer';
import CapitalFlowPanel from './CapitalFlowPanel';
import LcLineChart from './charts/LcLineChart';
import ErrorState from './ui/ErrorState';

type StatusFilter = '' | 'wired' | 'catalog';

function toolCallSnippet(item: QuantStrategyItem, symbol: string): string {
  const strategy = item.engine || item.id;
  return `{"tool": "market_backtest", "args": {"symbol": "${symbol}", "strategy": "${strategy}"}}`;
}

function parentCheckState(group: QuantStrategyGroup, selected: Set<string>): 'all' | 'some' | 'none' {
  const wired = group.items.filter((row) => row.status === 'wired');
  if (!wired.length) return 'none';
  const n = wired.filter((row) => selected.has(row.id)).length;
  if (n === 0) return 'none';
  if (n === wired.length) return 'all';
  return 'some';
}

function pct(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function num(value?: number | null, digits = 2): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}

export default function StrategyCatalogPanel({ embedded = false }: { embedded?: boolean }) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<StatusFilter>('');
  const [data, setData] = useState<Awaited<ReturnType<typeof labQuantStrategies>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [activeId, setActiveId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [symbol, setSymbol] = useState('600519');
  const [appliedSymbol, setAppliedSymbol] = useState('600519');
  const [preview, setPreview] = useState<QuantStrategyPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void labQuantStrategies()
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setError(null);
        const next: Record<string, boolean> = {};
        (payload.groups ?? []).forEach((group, idx) => {
          next[group.id] = idx === 0;
        });
        setOpen(next);
        setSelected(new Set());
        const first =
          payload.groups?.flatMap((group) => group.items).find((row) => row.status === 'wired') ??
          payload.groups?.[0]?.items?.[0];
        if (first) setActiveId(first.id);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadTick]);

  useEffect(() => {
    if (!activeId) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    setPreviewError(null);
    void labArchifyStrategy(activeId)
      .then((payload) => {
        if (cancelled) return;
        setPreview((prev) => ({
          ...payload,
          symbol: appliedSymbol,
          chart: prev?.item?.id === payload.item.id ? prev.chart : null,
        }));
      })
      .catch((err) => {
        if (cancelled) return;
        setPreview(null);
        setPreviewError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, appliedSymbol]);

  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    setChartLoading(true);
    void labQuantPreview(activeId, appliedSymbol)
      .then((payload) => {
        if (cancelled) return;
        setPreview((prev) => ({
          ...(prev ?? payload),
          ...payload,
        }));
      })
      .catch(() => {
        /* 工作流仍顯示；曲線區自己處理空資料 */
      })
      .finally(() => {
        if (!cancelled) setChartLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId, appliedSymbol]);

  const q = query.trim().toLowerCase();
  const groups = useMemo(() => {
    const source = data?.groups ?? [];
    return source
      .map((group) => {
        const items = group.items.filter((row) => {
          if (status && row.status !== status) return false;
          if (!q) return true;
          return (
            q === group.id ||
            group.name.toLowerCase().includes(q) ||
            row.id.includes(q) ||
            row.name.toLowerCase().includes(q)
          );
        });
        return { ...group, items, total: items.length, wired: items.filter((row) => row.status === 'wired').length };
      })
      .filter((group) => group.items.length > 0);
  }, [data?.groups, q, status]);

  const active = useMemo(() => {
    for (const group of groups) {
      const hit = group.items.find((row) => row.id === activeId);
      if (hit) return hit;
    }
    return groups[0]?.items[0] ?? null;
  }, [activeId, groups]);

  const selectedCount = selected.size;
  const wiredVisible = groups.flatMap((group) => group.items.filter((row) => row.status === 'wired'));

  function toggleItem(item: QuantStrategyItem) {
    if (item.status !== 'wired') {
      setActiveId(item.id);
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
    setActiveId(item.id);
  }

  function toggleGroup(group: QuantStrategyGroup) {
    const wired = group.items.filter((row) => row.status === 'wired');
    if (!wired.length) return;
    const state = parentCheckState(group, selected);
    setSelected((prev) => {
      const next = new Set(prev);
      if (state === 'all') wired.forEach((row) => next.delete(row.id));
      else wired.forEach((row) => next.add(row.id));
      return next;
    });
  }

  async function copySnippet(item: QuantStrategyItem) {
    const text = toolCallSnippet(item, appliedSymbol);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  function applySymbol() {
    const next = symbol.trim() || '600519';
    setSymbol(next);
    setAppliedSymbol(next);
  }

  const chart = preview?.chart?.ok === false ? null : preview?.chart;
  const series = chart?.chart;
  const equityPoints = (series?.equity ?? []).map((row, i) => ({ x: i, y: row.v }));
  const holdPoints = (series?.hold ?? []).map((row, i) => ({ x: i, y: row.v }));
  const closePoints = (series?.close ?? []).map((row, i) => ({ x: i, y: row.v }));

  if (loading) {
    return <p className="py-8 text-center text-[12px] text-[#8E8E93]">載入策略庫…</p>;
  }
  if (error) {
    return <ErrorState kind="partial" message={error} onRetry={() => setReloadTick((n) => n + 1)} />;
  }

  const chartFail = preview?.chart && preview.chart.ok === false ? preview.chart.error : null;

  return (
    <div className={embedded ? 'sq-map sq-tree-embed' : 'sq-map'}>
      <section className="sq-tree-card">
        <header className="sq-tree-head">
          <div className="sq-tree-title">
            策略庫
            <span className="sq-tree-badge">{selectedCount}</span>
          </div>
          <span className="text-[10px] text-[#636366]">
            {data?.wired_count ?? 0} 可回測 · {data?.catalog_count ?? 0} 目錄
          </span>
        </header>
        <div className="sq-tree-tools">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜尋策略／分類"
            className="sq-tree-search"
          />
          {([
            ['', '全部'],
            ['wired', '可回測'],
            ['catalog', '規劃'],
          ] as const).map(([key, label]) => (
            <button
              key={key || 'all'}
              type="button"
              className={`sq-tree-chip ${status === key ? 'on' : ''}`}
              onClick={() => setStatus(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="sq-tree" role="tree" aria-label="回測策略庫">
          {groups.length === 0 ? (
            <p className="px-3 py-6 text-center text-[11px] text-[#636366]">沒有符合的策略</p>
          ) : (
            groups.map((group) => {
              const expanded = open[group.id] !== false;
              const check = parentCheckState(group, selected);
              return (
                <div key={group.id} className="sq-tree-group">
                  <div className="sq-tree-parent">
                    <button
                      type="button"
                      className="sq-tree-caret"
                      aria-expanded={expanded}
                      onClick={() => setOpen((prev) => ({ ...prev, [group.id]: !expanded }))}
                    >
                      {expanded ? '▼' : '▶'}
                    </button>
                    <label className="sq-tree-check">
                      <input
                        type="checkbox"
                        checked={check === 'all'}
                        ref={(el) => {
                          if (el) el.indeterminate = check === 'some';
                        }}
                        disabled={group.wired === 0}
                        onChange={() => toggleGroup(group)}
                      />
                    </label>
                    <button
                      type="button"
                      className="sq-tree-parent-label"
                      onClick={() => setOpen((prev) => ({ ...prev, [group.id]: !expanded }))}
                    >
                      【{group.name}】
                      <span className="sq-tree-count">{group.wired}/{group.total}</span>
                    </button>
                  </div>
                  {expanded
                    ? group.items.map((item) => {
                        const on = item.status === 'wired' && selected.has(item.id);
                        const activeRow = active?.id === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            role="treeitem"
                            aria-selected={activeRow}
                            className={`sq-tree-leaf ${on ? 'on' : ''} ${activeRow ? 'cur' : ''}`}
                            onClick={() => toggleItem(item)}
                          >
                            <span className={`sq-box ${on ? 'on' : ''} ${item.status !== 'wired' ? 'off' : ''}`}>
                              {on ? '✓' : ''}
                            </span>
                            <span className="sq-tree-leaf-name">{item.name}</span>
                            <span className="sq-tree-id">{item.engine || item.id}</span>
                          </button>
                        );
                      })
                    : null}
                </div>
              );
            })
          )}
        </div>
      </section>

      <div className="sq-map-stage">
        <div className="sq-map-kinds">
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') applySymbol();
            }}
            placeholder="標的，如 600519"
            className="sq-chart-symbol"
            aria-label="回測標的"
          />
          <button type="button" className="sq-tree-chip on" onClick={applySymbol}>
            繪製回測
          </button>
        </div>
        {previewLoading ? (
          <p className="py-6 text-center text-[12px] text-[#8E8E93]">載入圖表…</p>
        ) : previewError ? (
          <ErrorState kind="partial" message={previewError} />
        ) : preview?.workflow ? (
          <ArchifyViewer ir={preview.workflow} compact={embedded} />
        ) : (
          <p className="py-6 text-center text-[11px] text-[#636366]">選策略後顯示工作流</p>
        )}
        <section className="apple-card sq-chart-card">
          <div className="apple-card__head">
            <h2 className="apple-title">權益曲線</h2>
            <span className="text-[10px] text-[#8E8E93]">{appliedSymbol}</span>
          </div>
          {chartFail ? (
            <p className="px-4 py-8 text-center text-[11px] text-[#636366]">{chartFail}</p>
          ) : chartLoading && !equityPoints.length ? (
            <p className="px-4 py-8 text-center text-[11px] text-[#8E8E93]">載入權益曲線…</p>
          ) : active?.status !== 'wired' ? (
            <p className="px-4 py-8 text-center text-[11px] text-[#636366]">規劃項沒有回測曲線</p>
          ) : equityPoints.length ? (
            <>
              <div className="sq-chart-stats">
                <div className="sq-chart-stat">
                  <p className="sq-chart-stat-k">報酬</p>
                  <p className="sq-chart-stat-v">{pct(chart?.total_return)}</p>
                </div>
                <div className="sq-chart-stat">
                  <p className="sq-chart-stat-k">最大回撤</p>
                  <p className="sq-chart-stat-v">{pct(chart?.max_drawdown)}</p>
                </div>
                <div className="sq-chart-stat">
                  <p className="sq-chart-stat-k">夏普</p>
                  <p className="sq-chart-stat-v">{num(chart?.sharpe)}</p>
                </div>
                <div className="sq-chart-stat">
                  <p className="sq-chart-stat-k">交易</p>
                  <p className="sq-chart-stat-v">{chart?.trades ?? '—'}</p>
                </div>
                <div className="sq-chart-stat">
                  <p className="sq-chart-stat-k">訊號</p>
                  <p className="sq-chart-stat-v">{chart?.last_signal ?? '—'}</p>
                </div>
              </div>
              {chart?.demo ? (
                <p className="px-4 pb-2 text-[10px] text-[#8E8E93]">{chart.note || '示範曲線（行情源暫時不可用）'}</p>
              ) : null}
              <div className="apple-card__body apple-card__body--static apple-chart h-[220px]">
                <LcLineChart
                  height={220}
                  series={[
                    { id: 'equity', name: '策略', color: '#0A84FF', points: equityPoints },
                    ...(holdPoints.length
                      ? [{ id: 'hold', name: '買入持有', color: '#8E8E93', points: holdPoints }]
                      : []),
                  ]}
                />
              </div>
            </>
          ) : (
            <p className="px-4 py-8 text-center text-[11px] text-[#636366]">尚無權益資料</p>
          )}
        </section>
        <section className="apple-card sq-chart-card">
          <div className="apple-card__head">
            <h2 className="apple-title">收盤價</h2>
            <span className="text-[10px] text-[#8E8E93]">K 線收盤</span>
          </div>
          {chartLoading && !closePoints.length ? (
            <p className="px-4 py-8 text-center text-[11px] text-[#8E8E93]">載入收盤價…</p>
          ) : closePoints.length ? (
            <div className="apple-card__body apple-card__body--static apple-chart h-[180px]">
              <LcLineChart
                height={180}
                series={[{ id: 'close', name: '收盤', color: '#34C759', points: closePoints }]}
              />
            </div>
          ) : (
            <p className="px-4 py-8 text-center text-[11px] text-[#636366]">尚無價格曲線</p>
          )}
        </section>
        <CapitalFlowPanel
          strategyId={active?.id ?? null}
          symbol={appliedSymbol}
          strategyName={active?.name}
          wired={active?.status === 'wired'}
        />
      </div>

      <aside className="sq-tree-side">
        <p className="sq-tree-side-k">角色引用</p>
        {active ? (
          <>
            <h3 className="sq-tree-side-title">{active.name}</h3>
            <p className="mt-1 font-mono text-[11px] text-[#8E8E93]">{active.engine || active.id}</p>
            <p className="mt-2 text-[11px] text-[#636366]">
              {active.status === 'wired'
                ? `可回測。量化分析師用 market_backtest.strategy = ${active.engine || active.id}`
                : '規劃項，尚未接通引擎，不可回測。'}
            </p>
            {active.status === 'wired' ? (
              <>
                <pre className="sq-tree-code">{toolCallSnippet(active, appliedSymbol)}</pre>
                <button type="button" className="sq-tree-copy" onClick={() => void copySnippet(active)}>
                  {copied ? '已複製' : '複製 tool_call'}
                </button>
              </>
            ) : null}
          </>
        ) : (
          <p className="text-[11px] text-[#636366]">勾選可回測策略，交給量化研究桌角色引用。</p>
        )}
        <p className="mt-4 text-[10px] leading-relaxed text-[#48484A]">
          已勾選 {selectedCount} / {wiredVisible.length} 可回測引擎。目錄項僅供對照 stock-quant 策略庫。
        </p>
        <a href="#/monitor/lab/maps" className="mt-3 block text-[11px] text-[#0A84FF]">
          用策略圖可視化全部策略
        </a>
      </aside>
    </div>
  );
}
