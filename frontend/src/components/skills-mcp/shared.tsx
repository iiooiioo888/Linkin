/**
 * 技能與 MCP 面板共用 UI：分層收合區塊、錯誤／成功提示列。
 */

import { useState, type ReactNode } from 'react';

export function TierSection({
  title,
  count,
  children,
  defaultOpen = true,
}: {
  title: string;
  count: number;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (count === 0) return null;
  return (
    <section className="mb-4">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="mb-2 flex w-full items-center justify-between rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2 text-left"
      >
        <span className="text-[11px] font-semibold text-[var(--console-ink)]">{title}</span>
        <span className="text-[10px] text-[var(--console-faint)]">{count} · {open ? '▾' : '▸'}</span>
      </button>
      {open ? children : null}
    </section>
  );
}

export function ErrorBar({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="mb-3 rounded-md border border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-3 py-2 text-xs console-status-danger">{message}</div>;
}

export function OkBar({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs console-status-green">{message}</div>;
}
