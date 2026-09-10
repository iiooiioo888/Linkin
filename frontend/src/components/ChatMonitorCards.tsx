/**
 * ChatMonitorCards — 對話／監控共用卡片（Apple 控制中心語彙）。
 * 標題 Bold、數據 Regular；狀態燈柔光圓點；色票 #007AFF / #34C759 / #FF9500 / #FF3B30。
 */
import { useState, type ReactNode } from 'react';

const ACCENT_CLS: Record<string, string> = {
  green: 'text-[#34C759]',
  amber: 'text-[#FF9500]',
  blue: 'text-[#007AFF]',
  orange: 'text-[#FF9500]',
  violet: 'text-[#64D2FF]',
  red: 'text-[#FF3B30]',
  cyan: 'text-[#64D2FF]',
};

export function TopKpi({
  label,
  value,
  hint,
  accent,
  pulse,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
  pulse?: boolean;
}) {
  return (
    <div
      className={`apple-card apple-card--tight apple-card--pad transition-shadow duration-300 ${
        pulse ? 'ring-1 ring-[#34C759]/30' : ''
      }`}
    >
      <p className="apple-title">{label}</p>
      <p className={`apple-data mt-2 truncate text-[22px] leading-none ${accent || 'text-[#F5F5F7]'}`}>
        {value}
      </p>
      {hint && <p className="mt-2 truncate text-[11px] font-normal text-[#8E8E93]">{hint}</p>}
    </div>
  );
}

export function MiniKpi({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: 'green' | 'amber' | 'blue' | 'orange' | 'violet' | 'red' | 'cyan';
}) {
  return (
    <div className="apple-card apple-card--tight apple-card--pad transition-colors duration-200 hover:border-white/15">
      <p className="apple-title !text-[10px]">{label}</p>
      <p className={`apple-data mt-1.5 text-[15px] ${accent ? ACCENT_CLS[accent] : 'text-[#F5F5F7]'}`}>
        {value}
      </p>
      {hint && <p className="mt-1 truncate text-[10px] font-normal text-[#636366]">{hint}</p>}
    </div>
  );
}

export function MonitorSection({
  title,
  hint,
  badge,
  children,
  scroll = false,
  maxHeight,
  defaultCollapsed = false,
}: {
  title: string;
  hint?: string;
  badge?: string;
  children: ReactNode;
  scroll?: boolean;
  maxHeight?: string;
  /** C-UI-001：預設折疊防過載 */
  defaultCollapsed?: boolean;
}) {
  const [open, setOpen] = useState(!defaultCollapsed);
  return (
    <section
      className="apple-card"
      style={scroll && maxHeight && open ? { maxHeight } : undefined}
    >
      <button
        type="button"
        className="apple-card__head w-full cursor-pointer text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className="flex min-w-0 items-center gap-2">
          <h4 className="apple-title">{title}</h4>
          {badge && (
            <span
              className={`rounded-md px-1.5 py-0.5 text-[9px] font-bold tracking-wide ${
                badge === 'LIVE'
                  ? 'bg-[#34C759]/15 text-[#34C759]'
                  : 'bg-white/5 text-[#8E8E93]'
              }`}
            >
              {badge}
            </span>
          )}
        </div>
        <span className="shrink-0 text-[10px] font-normal text-[#636366]">
          {hint ? `${hint} · ` : ''}{open ? '收合' : '展開'}
        </span>
      </button>
      {open ? (
        <div className={`apple-card__body ${scroll ? '' : 'apple-card__body--static'}`}>
          {children}
        </div>
      ) : null}
    </section>
  );
}

export function HealthPill({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean | null;
  detail?: string;
}) {
  const dotCls =
    ok === null ? 'apple-dot' : ok ? 'apple-dot apple-dot--ok' : 'apple-dot apple-dot--err';
  const text = ok === null ? 'text-[#8E8E93]' : ok ? 'text-[#34C759]' : 'text-[#FF3B30]';
  return (
    <div className="apple-inset flex items-center gap-2.5 px-3 py-2">
      <span className={dotCls} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-[12px] font-bold text-[#F5F5F7]">{label}</p>
        {detail && <p className={`truncate text-[11px] font-normal ${text}`}>{detail}</p>}
      </div>
    </div>
  );
}

export function LiveTicker({
  items,
}: {
  items: Array<{ key: string; text: string; ts?: string; accent?: string }>;
}) {
  if (items.length === 0) return null;
  return (
    <div className="apple-chrome shrink-0 overflow-hidden border-t">
      <div className="flex items-center gap-3 px-4 py-2">
        <span className="inline-flex items-center gap-1.5 shrink-0 text-[10px] font-bold uppercase tracking-wider text-[#34C759]">
          <span className="apple-dot apple-dot--live" />
          LIVE
        </span>
        <div className="min-w-0 flex-1 overflow-x-auto">
          <div className="flex gap-5 whitespace-nowrap">
            {items.map((it) => (
              <span key={it.key} className={`text-[11px] font-normal ${it.accent || 'text-[#AEAEB2]'}`}>
                {it.ts && <span className="mr-1 font-mono text-[#636366]">{it.ts}</span>}
                {it.text}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const ROADMAP_TONE: Record<string, string> = {
  P0: 'border-[#007AFF]/35 bg-[#007AFF]/10',
  P1: 'border-[#34C759]/30 bg-[#34C759]/08',
  P2: 'border-[#FF9500]/30 bg-[#FF9500]/08',
  P3: 'border-white/10 bg-white/[0.03]',
};

function roadmapStatusText(enabled: boolean, status: string): string {
  if (!enabled || status === 'disabled') return '停用';
  if (status === 'learning') return '學習';
  return '運行';
}

export function RoadmapChip({
  priority,
  label,
  benefit,
  enabled,
  status,
  compact,
  metric,
}: {
  priority: string;
  label: string;
  benefit?: string;
  enabled: boolean;
  status: string;
  compact?: boolean;
  metric?: string;
}) {
  const tone = ROADMAP_TONE[priority] ?? ROADMAP_TONE.P3;
  const active = enabled && status !== 'disabled';
  return (
    <div
      className={`rounded-2xl border px-3 py-2 ${tone} ${active ? '' : 'opacity-55'}`}
      title={benefit}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="text-[9px] font-bold text-[#8E8E93]">{priority}</span>
        <span className={`text-[9px] font-normal ${active ? 'text-[#34C759]' : 'text-[#636366]'}`}>
          {roadmapStatusText(enabled, status)}
        </span>
      </div>
      <p className={`mt-1 truncate font-bold ${compact ? 'text-[11px]' : 'text-[12px]'} text-[#F5F5F7]`}>
        {label}
      </p>
      {metric && (
        <p className="apple-data mt-1 truncate text-[10px] text-[#636366]">{metric}</p>
      )}
      {benefit && !compact && !metric && (
        <p className="mt-1 truncate text-[10px] font-normal text-[#636366]">{benefit}</p>
      )}
    </div>
  );
}

export function RoadmapTable({
  items,
  compact,
}: {
  items: Array<{
    id: string;
    priority: string;
    label: string;
    benefit?: string;
    enabled: boolean;
    status: string;
    metric?: string;
  }>;
  compact?: boolean;
}) {
  if (!items.length) return null;
  if (compact) {
    return (
      <div className="mb-3 grid grid-cols-2 gap-2">
        {items.map((it) => (
          <RoadmapChip key={it.id} {...it} compact metric={it.metric} />
        ))}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-2xl border border-white/[0.08]">
      <table className="w-full text-left">
        <thead className="bg-black/25 text-[10px] font-bold uppercase tracking-wider text-[#8E8E93]">
          <tr>
            <th className="px-3 py-2">優先</th>
            <th className="px-3 py-2">項目</th>
            <th className="px-3 py-2">狀態</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it) => (
            <tr key={it.id} className="border-t border-white/[0.06]">
              <td className="apple-data px-3 py-2.5 text-[11px] text-[#007AFF]">{it.priority}</td>
              <td className="px-3 py-2.5 text-[12px] font-bold text-[#F5F5F7]">
                {it.label}
                {it.benefit && (
                  <span className="mt-0.5 block text-[11px] font-normal text-[#636366]">{it.benefit}</span>
                )}
              </td>
              <td className="px-3 py-2.5 text-[11px] font-normal text-[#8E8E93]">
                {roadmapStatusText(it.enabled, it.status)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
