/**
 * /context peek 浮動預覽 — 次級入口。
 * 主表面在對話底部詳細區；必須綁定呼叫方傳入的 taskId。
 * **禁止**無 taskId 時回落 `/context` 全域最新軌跡（避免顯示其他對話）。
 */
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { fetchContextInsight, type ContextInsight } from '../api/contextInsight';
import { COMPOSITION_META, fmtPressure, fmtTokens, openChatContextDetail } from '../lib/contextUi';
import type { CompositionKey } from '../api/contextInsight';

const KEYS: CompositionKey[] = ['system', 'tools', 'user', 'injected', 'assistant', 'tool_results'];

function emptyPeek(message: string): ContextInsight {
  return {
    task_id: null,
    empty: true,
    message,
    stats: {},
    composition: {},
    trend: [],
    events: [],
    steps: [],
    selected_step: null,
    browser: { step: null, categories: {} },
  };
}

export default function ContextModal({
  open,
  taskId,
  onClose,
}: {
  open: boolean;
  /** 綁定的對話任務；null／空＝本對話尚無軌跡，絕不抓其他會話 */
  taskId?: string | null;
  onClose: () => void;
}) {
  const [data, setData] = useState<ContextInsight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openItem, setOpenItem] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setError(null);
    setOpenItem(null);
    const bound = (taskId || '').trim();
    if (!bound) {
      setData(
        emptyPeek('本對話尚無任務軌跡。Context Peek 僅顯示當前對話，不會載入其他會話。'),
      );
      return () => {
        cancelled = true;
      };
    }
    void fetchContextInsight({ taskId: bound })
      .then((d) => {
        if (cancelled) return;
        // 防禦：若後端誤回其他 task，仍以請求 ID 為準並標空
        if (d.task_id && d.task_id !== bound) {
          setData(emptyPeek('軌跡與當前對話不符，已拒絕顯示其他會話 Context。'));
          return;
        }
        setData(d);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [open, taskId]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const composition = data?.composition || {};
  const total = KEYS.reduce((s, k) => s + (composition[k]?.tokens || 0), 0) || 1;
  const boundId = (taskId || '').trim() || data?.task_id || null;

  return createPortal(
    <div className="ctx-modal-root" role="dialog" aria-modal="true" aria-label="Context">
      <button type="button" className="ctx-modal-backdrop" aria-label="關閉" onClick={onClose} />
      <div className="ctx-modal">
        <header className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold text-[#F5F5F7]">/context peek</h2>
            <p className="mt-0.5 text-[11px] text-[#8E8E93]">
              當前對話預覽 · 完整面板在對話底部詳細區
              {boundId ? ` · ${boundId.slice(0, 10)}…` : ' · 未綁定任務'}
              {data?.stats?.context_pressure != null
                ? ` · 壓力 ${fmtPressure(data.stats.context_pressure)}`
                : ''}
            </p>
            <span
              className="mt-1 inline-block rounded-full border border-white/[0.08] px-2 py-0.5 font-mono text-[10px] text-[#AEAEB2]"
              data-testid="context-peek-locked"
            >
              {boundId ? `本對話 · ${boundId.slice(0, 12)}…` : '本對話 · 尚無任務'}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded-xl border border-white/[0.08] px-2.5 py-1 text-[11px] text-[#64D2FF]"
              onClick={() => {
                openChatContextDetail(boundId);
                onClose();
              }}
            >
              對話詳細區 →
            </button>
            <button
              type="button"
              className="rounded-xl border border-white/[0.08] px-2.5 py-1 text-[11px] text-[#8E8E93]"
              onClick={onClose}
            >
              關閉
            </button>
          </div>
        </header>

        {error ? <p className="mt-3 text-[12px] text-red-300">{error}</p> : null}
        {data?.empty ? <p className="mt-3 text-[12px] text-[#8E8E93]">{data.message}</p> : null}

        <div className="ctx-stack mt-4">
          {KEYS.map((k) => {
            const tok = composition[k]?.tokens || 0;
            if (!tok) return null;
            return (
              <span
                key={k}
                className="ctx-stack-seg"
                style={{ width: `${(tok / total) * 100}%`, background: COMPOSITION_META[k].color }}
                title={`${COMPOSITION_META[k].label} · ${fmtTokens(tok)}`}
              />
            );
          })}
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-[#AEAEB2]">
          {KEYS.map((k) => {
            const slice = composition[k];
            if (!slice?.tokens) return null;
            const delta = data?.browser?.vs_previous?.deltas?.[k]?.tokens ?? 0;
            return (
              <span key={k} className="inline-flex items-center gap-1">
                <i className="inline-block h-2 w-2 rounded-sm" style={{ background: COMPOSITION_META[k].color }} />
                {COMPOSITION_META[k].short} {fmtTokens(slice.tokens)}
                {delta !== 0 ? (
                  <span className={`ctx-delta ${delta > 0 ? 'is-up' : 'is-down'}`}>
                    {delta > 0 ? '+' : ''}
                    {fmtTokens(delta)}
                  </span>
                ) : null}
              </span>
            );
          })}
        </div>
        {data?.events?.length ? (
          <p className="mt-2 text-[10px] text-[#636366]">
            最近事件 {data.events.length} · Inject/Prune/Switch 詳見對話詳細區
          </p>
        ) : null}

        <div className="mt-4 max-h-[42vh] space-y-2 overflow-auto">
          {KEYS.map((k) => {
            const items = data?.browser?.categories?.[k] || [];
            if (!items.length) return null;
            return (
              <div key={k} className="rounded-lg border border-white/[0.06] bg-black/30 p-2">
                <p className="mb-1 text-[11px] font-medium text-[#F5F5F7]">{COMPOSITION_META[k].label}</p>
                {items.slice(0, 8).map((item) => (
                  <div key={item.id}>
                    <button
                      type="button"
                      className="flex w-full justify-between gap-2 px-1 py-1 text-left text-[11px] text-[#AEAEB2] hover:text-[#F5F5F7]"
                      onClick={() => setOpenItem((v) => (v === item.id ? null : item.id))}
                    >
                      <span className="truncate">{item.label}</span>
                      <span className="font-mono text-[10px]">{fmtTokens(item.tokens)}</span>
                    </button>
                    {openItem === item.id ? (
                      <pre className="mb-2 max-h-28 overflow-auto rounded bg-black/50 p-2 text-[10px] text-[#8E8E93]">
                        {item.content}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>,
    document.body,
  );
}
