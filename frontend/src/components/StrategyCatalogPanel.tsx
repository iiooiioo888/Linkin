/**
 * stock-quant 策略庫 — 分類樹，勾選可回測項交給角色 tool_call。
 */
import { useEffect, useMemo, useState } from 'react';
import { labQuantStrategies, type QuantStrategyGroup, type QuantStrategyItem } from '../api/client';
import ErrorState from './ui/ErrorState';

type StatusFilter = '' | 'wired' | 'catalog';

function toolCallSnippet(item: QuantStrategyItem): string {
  const strategy = item.engine || item.id;
  return `{"tool": "market_backtest", "args": {"symbol": "600519", "strategy": "${strategy}"}}`;
}

function parentCheckState(group: QuantStrategyGroup, selected: Set<string>): 'all' | 'some' | 'none' {
  const wired = group.items.filter((row) => row.status === 'wired');
  if (!wired.length) return 'none';
  const n = wired.filter((row) => selected.has(row.id)).length;
  if (n === 0) return 'none';
  if (n === wired.length) return 'all';
  return 'some';
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
        const first = payload.groups?.[0]?.items?.[0];
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
  }, []);

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
    const text = toolCallSnippet(item);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  if (loading) {
    return <p className="py-8 text-center text-[12px] text-[#8E8E93]">載入策略庫…</p>;
  }
  if (error) {
    return <ErrorState kind="partial" message={error} />;
  }

  return (
    <div className={`grid gap-4 ${embedded ? 'sq-tree-embed' : 'mx-auto max-w-5xl lg:grid-cols-[minmax(0,1fr)_280px]'}`}>
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
                <pre className="sq-tree-code">{toolCallSnippet(active)}</pre>
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
