/**
 * 策略可視化 — Archify 把策略庫總覽、分類拓撲與單策略工作流畫出來。
 */
import { useEffect, useMemo, useState } from 'react';
import {
  labArchifyStrategies,
  labArchifyStrategy,
  type ArchifyIR,
  type QuantStrategyItem,
  type StrategyMapCatalog,
  type StrategyMapDetail,
} from '../api/client';
import ArchifyFrame from './ArchifyFrame';
import ErrorState from './ui/ErrorState';

type Kind = 'architecture' | 'workflow' | 'lifecycle' | 'data-flow';

function toolCallSnippet(item: QuantStrategyItem): string {
  const strategy = item.engine || item.id;
  return `{"tool": "market_backtest", "args": {"symbol": "600519", "strategy": "${strategy}"}}`;
}

function archifySnippet(view: string, id?: string): string {
  const args = id ? `"view": "${view}", "id": "${id}"` : `"view": "${view}"`;
  return `{"tool": "archify_strategies", "args": {${args}}}`;
}

export default function StrategyMapPanel() {
  const [data, setData] = useState<StrategyMapCatalog | null>(null);
  const [detail, setDetail] = useState<StrategyMapDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [scope, setScope] = useState<'overview' | 'data_flow' | 'lifecycle' | string>('overview');
  const [kind, setKind] = useState<Kind>('architecture');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void labArchifyStrategies()
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setError(null);
        const next: Record<string, boolean> = {};
        (payload.groups ?? []).forEach((group, idx) => {
          next[group.id] = idx === 0;
        });
        setOpen(next);
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

  const q = query.trim().toLowerCase();
  const groups = useMemo(() => {
    const source = data?.groups ?? [];
    return source
      .map((group) => {
        const items = group.items.filter((row) => {
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
  }, [data?.groups, q]);

  const activeItem = useMemo(() => {
    if (!activeId) return null;
    for (const group of data?.groups ?? []) {
      const hit = group.items.find((row) => row.id === activeId);
      if (hit) return hit;
    }
    return detail?.item ?? null;
  }, [activeId, data?.groups, detail?.item]);

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    void labArchifyStrategy(activeId)
      .then((payload) => {
        if (!cancelled) setDetail(payload);
      })
      .catch(() => {
        if (!cancelled) setDetail(null);
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const ir: ArchifyIR | null = useMemo(() => {
    if (!data) return null;
    if (scope === 'overview') return data.overview;
    if (scope === 'data_flow') return data.data_flow;
    if (scope === 'lifecycle' && !activeId) return data.lifecycle;
    if (scope.startsWith('group:')) {
      const gid = scope.slice(6);
      return data.groups.find((g) => g.id === gid)?.architecture ?? data.overview;
    }
    if (activeId && detail) {
      if (kind === 'workflow') return detail.workflow;
      if (kind === 'lifecycle') return detail.lifecycle;
      return detail.architecture;
    }
    return data.overview;
  }, [activeId, data, detail, kind, scope]);

  function selectOverview() {
    setScope('overview');
    setKind('architecture');
    setActiveId(null);
  }

  function selectGroup(groupId: string) {
    setScope(`group:${groupId}`);
    setKind('architecture');
    setActiveId(null);
    setOpen((prev) => ({ ...prev, [groupId]: true }));
  }

  function selectStrategy(item: QuantStrategyItem) {
    setActiveId(item.id);
    setScope(`strategy:${item.id}`);
    setKind('workflow');
    setOpen((prev) => ({ ...prev, [item.category]: true }));
  }

  function onDiagramSelect(nodeId: string) {
    if (nodeId.startsWith('cat_')) {
      selectGroup(nodeId.slice(4));
      return;
    }
    if (nodeId.startsWith('hub_')) {
      selectGroup(nodeId.slice(4));
      return;
    }
    for (const group of data?.groups ?? []) {
      if (group.items.some((row) => row.id === nodeId)) {
        const item = group.items.find((row) => row.id === nodeId);
        if (item) selectStrategy(item);
        return;
      }
    }
  }

  async function copyText(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  if (loading) {
    return <p className="py-8 text-center text-[12px] text-[#8E8E93]">載入策略圖…</p>;
  }
  if (error) {
    return <ErrorState kind="partial" message={error} onRetry={() => setReloadTick((n) => n + 1)} />;
  }

  const kindBtns: Array<[Kind, string]> = activeId
    ? [
        ['workflow', '工作流'],
        ['lifecycle', '生命週期'],
        ['architecture', '所屬分類'],
      ]
    : [
        ['architecture', '總覽'],
        ['data-flow', '資料流'],
        ['lifecycle', '生命週期'],
      ];

  return (
    <div className="sq-map">
      <section className="sq-tree-card">
        <header className="sq-tree-head">
          <div className="sq-tree-title">
            策略圖
            <span className="sq-tree-badge">{data?.catalog_count ?? 0}</span>
          </div>
          <span className="text-[10px] text-[#636366]">
            {data?.wired_count ?? 0} 可回測 · Archify
          </span>
        </header>
        <div className="sq-tree-tools">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜尋策略／分類"
            className="sq-tree-search"
          />
          <button
            type="button"
            className={`sq-tree-chip ${scope === 'overview' ? 'on' : ''}`}
            onClick={selectOverview}
          >
            總覽
          </button>
          <button
            type="button"
            className={`sq-tree-chip ${scope === 'data_flow' ? 'on' : ''}`}
            onClick={() => {
              setScope('data_flow');
              setKind('data-flow');
              setActiveId(null);
            }}
          >
            資料流
          </button>
        </div>
        <div className="sq-tree" role="tree" aria-label="策略可視化分類">
          {groups.map((group) => {
            const expanded = open[group.id] !== false;
            const groupOn = scope === `group:${group.id}`;
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
                  <button
                    type="button"
                    className={`sq-tree-parent-label ${groupOn ? 'on' : ''}`}
                    onClick={() => selectGroup(group.id)}
                  >
                    【{group.name}】
                    <span className="sq-tree-count">
                      {group.wired}/{group.total}
                    </span>
                  </button>
                </div>
                {expanded
                  ? group.items.map((item) => {
                      const cur = activeId === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          role="treeitem"
                          aria-selected={cur}
                          className={`sq-tree-leaf ${cur ? 'cur' : ''}`}
                          onClick={() => selectStrategy(item)}
                        >
                          <span className={`sq-box ${item.status === 'wired' ? 'on' : 'off'}`}>
                            {item.status === 'wired' ? '✓' : ''}
                          </span>
                          <span className="sq-tree-leaf-name">{item.name}</span>
                          <span className="sq-tree-id">{item.engine || item.id}</span>
                        </button>
                      );
                    })
                  : null}
              </div>
            );
          })}
        </div>
      </section>

      <div className="sq-map-stage">
        <div className="sq-map-kinds">
          {kindBtns.map(([key, label]) => {
            const on =
              (key === 'data-flow' && scope === 'data_flow') ||
              (key === 'architecture' && !activeId && scope === 'overview') ||
              (key === 'architecture' && Boolean(activeId) && kind === 'architecture') ||
              (key === 'workflow' && kind === 'workflow' && Boolean(activeId)) ||
              (key === 'lifecycle' &&
                ((kind === 'lifecycle' && Boolean(activeId)) || (scope === 'lifecycle' && !activeId)));
            return (
              <button
                key={key}
                type="button"
                className={`sq-tree-chip ${on ? 'on' : ''}`}
                onClick={() => {
                  if (key === 'data-flow') {
                    setScope('data_flow');
                    setKind('data-flow');
                    setActiveId(null);
                    return;
                  }
                  if (key === 'architecture' && !activeId) {
                    selectOverview();
                    return;
                  }
                  if (key === 'lifecycle' && !activeId) {
                    setScope('lifecycle');
                    setKind('lifecycle');
                    return;
                  }
                  setKind(key);
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
        {detailLoading && activeId ? (
          <p className="py-6 text-center text-[12px] text-[#8E8E93]">載入工作流…</p>
        ) : (
          <ArchifyFrame
            view={
              activeId
                ? 'strategy'
                : scope.startsWith('group:')
                  ? 'group'
                  : scope === 'data_flow'
                    ? 'data_flow'
                    : scope === 'lifecycle'
                      ? 'lifecycle'
                      : 'overview'
            }
            id={activeId ?? (scope.startsWith('group:') ? scope.slice(6) : undefined)}
            kind={activeId ? kind : undefined}
            fallbackIr={ir}
            focusId={activeId}
            onSelect={onDiagramSelect}
          />
        )}
      </div>

      <aside className="sq-tree-side">
        <p className="sq-tree-side-k">角色引用</p>
        {activeItem ? (
          <>
            <h3 className="sq-tree-side-title">{activeItem.name}</h3>
            <p className="mt-1 font-mono text-[11px] text-[#8E8E93]">{activeItem.engine || activeItem.id}</p>
            <p className="mt-2 text-[11px] text-[#636366]">
              {detail?.hint ||
                (activeItem.status === 'wired'
                  ? `可回測。量化分析師用 market_backtest.strategy = ${activeItem.engine || activeItem.id}`
                  : '規劃項，尚未接通引擎，不可回測。')}
            </p>
            {activeItem.status === 'wired' ? (
              <pre className="sq-tree-code">{toolCallSnippet(activeItem)}</pre>
            ) : null}
            <pre className="sq-tree-code">{archifySnippet('strategy', activeItem.id)}</pre>
            <button
              type="button"
              className="sq-tree-copy"
              onClick={() =>
                void copyText(
                  activeItem.status === 'wired'
                    ? toolCallSnippet(activeItem)
                    : archifySnippet('strategy', activeItem.id),
                )
              }
            >
              {copied ? '已複製' : '複製 tool_call'}
            </button>
            <a href="#/monitor/lab/quant" className="mt-3 block text-[11px] text-[#0A84FF]">
              回策略庫分類樹
            </a>
          </>
        ) : (
          <>
            <h3 className="sq-tree-side-title">全部策略可視化</h3>
            <p className="mt-2 text-[11px] text-[#636366]">
              {data?.hint || '點分類看該類全部策略節點；點策略看工作流與生命週期。'}
            </p>
            <pre className="sq-tree-code">
              {scope.startsWith('group:')
                ? archifySnippet('group', scope.slice(6))
                : archifySnippet(scope === 'data_flow' ? 'data_flow' : scope === 'lifecycle' ? 'lifecycle' : 'overview')}
            </pre>
            <button
              type="button"
              className="sq-tree-copy"
              onClick={() =>
                void copyText(
                  archifySnippet(
                    scope.startsWith('group:') ? 'group' : scope === 'data_flow' ? 'data_flow' : scope,
                    scope.startsWith('group:') ? scope.slice(6) : undefined,
                  ),
                )
              }
            >
              {copied ? '已複製' : '複製 archify_strategies'}
            </button>
            <a href="#/monitor/lab/quant" className="mt-3 block text-[11px] text-[#0A84FF]">
              策略庫勾選回測
            </a>
          </>
        )}
      </aside>
    </div>
  );
}
