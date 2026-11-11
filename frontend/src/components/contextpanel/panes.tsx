/**
 * Context 面板資料窗格：檔案活動、席位網、Context Browser。
 */
import { useState } from 'react';
import type {
  CompositionKey,
  ContextAgentNode,
  ContextFileActivity,
  ContextInsight,
  FilePurpose,
} from '../../api/contextInsight';
import { COMPOSITION_META, FILE_PURPOSE_META, fmtTokens, sourceChipTone } from '../../lib/contextUi';
import type { BrowserSort } from '../../lib/contextUi';
import { btnCls, FILE_FILTERS, KEYS } from './utils';

export function FileActivityPane({ rows }: { rows: ContextFileActivity[] }) {
  const [filter, setFilter] = useState<FilePurpose | 'all'>('all');
  const [openPath, setOpenPath] = useState<string | null>(null);
  const filtered = rows.filter((r) => filter === 'all' || r.purposes.includes(filter));
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {FILE_FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`${btnCls}${filter === f ? ' !text-[var(--console-accent)]' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f === 'all' ? '全部' : FILE_PURPOSE_META[f].label}
          </button>
        ))}
      </div>
      {!filtered.length ? (
        <p className="text-[11px] text-[var(--console-sub)]">尚無檔案讀寫／搜尋活動。</p>
      ) : (
        <ul className="max-h-72 space-y-1 overflow-auto">
          {filtered.map((row) => (
            <li key={row.path} className="rounded-lg border border-white/[0.04] bg-black/20">
              <button
                type="button"
                className="flex w-full items-start justify-between gap-2 px-2 py-1.5 text-left"
                onClick={() => setOpenPath((v) => (v === row.path ? null : row.path))}
              >
                <div className="min-w-0">
                  <p className="truncate font-mono text-[11px] text-[var(--console-ink)]">{row.path}</p>
                  <div className="mt-0.5 flex flex-wrap gap-1.5 text-[10px]">
                    {row.purposes.map((p) => (
                      <span key={p} className={FILE_PURPOSE_META[p as FilePurpose]?.tone || 'text-[var(--console-sub)]'}>
                        {FILE_PURPOSE_META[p as FilePurpose]?.label || p}
                      </span>
                    ))}
                    <span className="text-[var(--console-sub)]">{row.ops_count} ops</span>
                  </div>
                </div>
                <div className="shrink-0 text-right font-mono text-[10px] text-[var(--console-sub)]">
                  {(row.added || row.removed) ? (
                    <span>
                      +{row.added}/−{row.removed}
                    </span>
                  ) : row.hits ? (
                    <span>{row.hits} hits</span>
                  ) : (
                    <span>—</span>
                  )}
                </div>
              </button>
              {openPath === row.path && row.ops?.length ? (
                <ul className="border-t border-white/[0.04] px-2 py-1.5 text-[10px] text-[var(--console-sub)]">
                  {row.ops.map((op, i) => (
                    <li key={`${op.seq}-${i}`} className="flex justify-between gap-2 py-0.5">
                      <span>
                        {op.tool} · {op.purpose}
                      </span>
                      <span className="font-mono text-[var(--console-sub)]">{op.ts ? String(op.ts).slice(11, 19) : ''}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function AgentNetworkPane({ nodes }: { nodes: ContextAgentNode[] }) {
  if (!nodes.length) {
    return <p className="text-[11px] text-[var(--console-sub)]">尚無席位呼叫紀錄。</p>;
  }
  const maxTok = Math.max(1, ...nodes.map((n) => (n.tokens_in || 0) + (n.tokens_out || 0)));
  return (
    <div className="ctx-agent-net">
      {nodes.map((n) => {
        const tok = (n.tokens_in || 0) + (n.tokens_out || 0);
        const occ = Math.round((tok / maxTok) * 100);
        return (
          <div key={n.role} className="ctx-agent-node" title={`${n.role} · ${fmtTokens(tok)}`}>
            <div className="ctx-agent-ring" style={{ ['--p' as string]: occ }} />
            <div className="min-w-0">
              <p className="truncate text-[12px] font-medium text-[var(--console-ink)]">{n.role}</p>
              <p className="text-[10px] text-[var(--console-sub)]">
                {n.llm_calls} 次 · {fmtTokens(tok)} · ${(n.cost || 0).toFixed(4)}
              </p>
              {n.parent ? <p className="text-[10px] text-[var(--console-sub)]">← {n.parent}</p> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function BrowserPane({
  browser,
  onJumpLive,
  isLive,
}: {
  browser: ContextInsight['browser'];
  onJumpLive?: () => void;
  isLive?: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState<CompositionKey | 'all'>('all');
  const [sort, setSort] = useState<BrowserSort>('size');
  const [query, setQuery] = useState('');

  const sortItems = (items: NonNullable<ContextInsight['browser']['categories'][CompositionKey]>) => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? items.filter(
          (it) =>
            it.label.toLowerCase().includes(q) ||
            String(it.source || '')
              .toLowerCase()
              .includes(q) ||
            String(it.content || '')
              .toLowerCase()
              .includes(q),
        )
      : items;
    const copy = [...filtered];
    if (sort === 'name') {
      copy.sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'));
    } else {
      copy.sort((a, b) => (b.tokens || 0) - (a.tokens || 0));
    }
    return copy;
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          className={`${btnCls}${isLive ? ' !text-[var(--console-green)]' : ''}`}
          onClick={() => onJumpLive?.()}
          title="Live＝最新一步（下一請求組成）"
        >
          Live
        </button>
        <button
          type="button"
          className={`${btnCls}${catFilter === 'all' ? ' !text-[var(--console-accent)]' : ''}`}
          onClick={() => setCatFilter('all')}
        >
          全部
        </button>
        {KEYS.map((k) => (
          <button
            key={k}
            type="button"
            className={`${btnCls}${catFilter === k ? ' !text-[var(--console-accent)]' : ''}`}
            onClick={() => setCatFilter(k)}
          >
            {COMPOSITION_META[k].short}
          </button>
        ))}
        <span className="mx-1 h-4 w-px bg-white/10" />
        <button
          type="button"
          className={`${btnCls}${sort === 'size' ? ' !text-[var(--console-accent)]' : ''}`}
          onClick={() => setSort('size')}
        >
          依大小
        </button>
        <button
          type="button"
          className={`${btnCls}${sort === 'name' ? ' !text-[var(--console-accent)]' : ''}`}
          onClick={() => setSort('name')}
        >
          依名稱
        </button>
      </div>
      <input
        className="w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[11px] text-[var(--console-ink)] outline-none focus:border-[color-mix(in_srgb,var(--console-accent)_50%,transparent)]"
        placeholder="篩選標籤／來源／內容…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {KEYS.filter((k) => catFilter === 'all' || catFilter === k).map((k) => {
        const items = sortItems(browser.categories?.[k] || []);
        if (!items.length) return null;
        return (
          <div key={k} id={`ctx-browser-${k}`} className="rounded-lg border border-white/[0.06] bg-black/20 p-2">
            <div className="mb-1 flex items-center gap-2 text-[11px] font-medium text-[var(--console-ink)]">
              <i className="inline-block h-2 w-2 rounded-sm" style={{ background: COMPOSITION_META[k].color }} />
              {COMPOSITION_META[k].label}
              <span className="text-[var(--console-sub)]">{items.length}</span>
            </div>
            <ul className="space-y-1">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className="flex w-full items-center justify-between gap-2 rounded-md px-2 py-1 text-left text-[11px] text-[var(--console-sub)] hover:bg-white/[0.04]"
                    onClick={() => setOpenId((v) => (v === item.id ? null : item.id))}
                  >
                    <span className="min-w-0 truncate">
                      <span className="text-[var(--console-ink)]">{item.label}</span>
                      <span className={`ml-2 ${sourceChipTone(item.source)}`}>{item.source}</span>
                    </span>
                    <span className="shrink-0 font-mono text-[10px]">{fmtTokens(item.tokens)}</span>
                  </button>
                  {openId === item.id ? (
                    <pre className="mt-1 max-h-40 overflow-auto rounded-md border border-white/[0.06] bg-black/40 p-2 text-[10px] leading-relaxed text-[var(--console-sub)]">
                      {item.content || '（空）'}
                    </pre>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
