/**
 * 任務詳情整頁共用的小節元件。
 * 樣式一律走 index.css 既有的 --apple-* token 與 utility class，
 * 本頁不新增任何 CSS 檔案。
 */
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

export const CARD_CLS =
  'rounded-[7px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] p-2.5';

export const LABEL_CLS =
  'text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--apple-tertiary)]';

/** 區塊標題（左側導航錨點對應的正文標題）。 */
export function SectionHead({
  index,
  title,
  hint,
  right,
}: {
  index: number;
  title: string;
  hint?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-2.5 flex items-baseline justify-between gap-3 border-b border-[var(--apple-hairline)] pb-2">
      <h3 className="flex items-baseline gap-2 text-[13px] font-semibold text-[var(--apple-label)]">
        <span className="apple-data text-[10px] font-normal text-[var(--apple-tertiary)]">
          {String(index).padStart(2, '0')}
        </span>
        {title}
        {hint ? (
          <span className="truncate text-[10.5px] font-normal text-[var(--apple-tertiary)]">{hint}</span>
        ) : null}
      </h3>
      {right ? <div className="shrink-0 text-[10.5px] text-[var(--apple-secondary)]">{right}</div> : null}
    </div>
  );
}

/** 小標（區塊內的分項標題）。 */
export function SubHead({ children, count }: { children: ReactNode; count?: number }) {
  return (
    <div className="mb-1.5 mt-3 flex items-center gap-1.5 first:mt-0">
      <span className={LABEL_CLS}>{children}</span>
      {typeof count === 'number' ? (
        <span className="apple-data text-[9px] text-[var(--apple-tertiary)]">{count}</span>
      ) : null}
    </div>
  );
}

/** 標籤／值 對。 */
export function Field({
  label,
  value,
  wide,
  tone,
}: {
  label: string;
  value?: ReactNode;
  wide?: boolean;
  tone?: string;
}) {
  const empty = value == null || value === '';
  return (
    <div className={`${CARD_CLS} ${wide ? 'sm:col-span-2' : ''} min-w-0`}>
      <div className={LABEL_CLS}>{label}</div>
      <div
        className="mt-1 break-words text-[12px] leading-relaxed text-[var(--apple-label)]"
        style={tone ? { color: tone } : undefined}
      >
        {empty ? <span className="text-[var(--apple-tertiary)]">—</span> : value}
      </div>
    </div>
  );
}

/** 兩欄欄位帶。 */
export function FieldGrid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">{children}</div>;
}

/** 通用卡片容器（tone 給左側色條與邊框著色）。 */
export function Card({
  children,
  className = '',
  tone,
}: {
  children: ReactNode;
  className?: string;
  tone?: string;
}) {
  return (
    <div
      className={`${CARD_CLS} min-w-0 ${className}`}
      style={tone ? { borderColor: `color-mix(in srgb, ${tone} 40%, transparent)` } : undefined}
    >
      {children}
    </div>
  );
}

export function Chip({ children, tone }: { children: ReactNode; tone?: string }) {
  return (
    <span
      className="apple-data inline-flex max-w-full items-center gap-1 rounded-[4px] border px-1.5 py-[1px] text-[10px] leading-[16px]"
      style={{
        borderColor: tone ? `color-mix(in srgb, ${tone} 45%, transparent)` : 'rgba(255,255,255,.10)',
        background: tone ? `color-mix(in srgb, ${tone} 12%, transparent)` : 'var(--apple-surface)',
        color: tone || 'var(--apple-secondary)',
      }}
    >
      {children}
    </span>
  );
}

export function ChipList({
  items,
  tone,
  empty,
}: {
  items: string[];
  tone?: string;
  empty?: string;
}) {
  if (!items.length) {
    return <span className="text-[11px] text-[var(--apple-tertiary)]">{empty || '無'}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((it, i) => (
        <Chip key={`${it}-${i}`} tone={tone}>
          {it}
        </Chip>
      ))}
    </div>
  );
}

/** 純 CSS 橫向條形（長條圖）。threshold 畫一道刻線。 */
export function ScoreBar({
  label,
  value,
  max = 100,
  threshold,
  tone,
  unit = '',
}: {
  label: ReactNode;
  value: number | null;
  max?: number;
  threshold?: number;
  tone?: string;
  unit?: string;
}) {
  const v = value == null ? 0 : Math.max(0, value);
  const width = max > 0 ? Math.min(100, (v / max) * 100) : 0;
  const color = tone || (value == null ? 'var(--apple-tertiary)' : width >= 90 ? 'var(--apple-green)' : width >= 60 ? 'var(--apple-orange)' : 'var(--apple-red)');
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="truncate text-[11px] text-[var(--apple-secondary)]">{label}</span>
        <span className="apple-data shrink-0 text-[11px] text-[var(--apple-label)]">
          {value == null ? '—' : `${Math.round(v * 10) / 10}${unit}`}
          {threshold != null ? (
            <span className="ml-1 text-[9px] text-[var(--apple-tertiary)]">/ 門檻 {threshold}</span>
          ) : null}
        </span>
      </div>
      <div className="relative h-[6px] w-full overflow-hidden rounded-full bg-[var(--apple-surface)]">
        <div
          className="h-full rounded-full transition-[width] duration-500"
          style={{ width: `${width}%`, background: color }}
        />
        {threshold != null && max > 0 ? (
          <span
            className="absolute top-0 h-full w-px bg-[var(--apple-label)]/45"
            style={{ left: `${Math.min(100, (threshold / max) * 100)}%` }}
            aria-hidden
          />
        ) : null}
      </div>
    </div>
  );
}

/** 細progressbar（預算／完成度通用）。 */
export function MiniBar({ ratio, tone }: { ratio: number; tone?: string }) {
  const w = Math.max(0, Math.min(100, ratio * 100));
  return (
    <div className="mt-1.5 h-[3px] w-full overflow-hidden rounded-full bg-[var(--apple-surface)]">
      <div
        className="h-full rounded-full"
        style={{ width: `${w}%`, background: tone || 'var(--apple-blue)' }}
      />
    </div>
  );
}

/** 有意義的空態（不留白）。 */
export function EmptyState({ title, note }: { title: string; note?: string }) {
  return (
    <div className="rounded-[7px] border border-dashed border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-3 py-4 text-center">
      <p className="text-[12px] text-[var(--apple-secondary)]">{title}</p>
      {note ? <p className="mt-1 text-[10.5px] leading-relaxed text-[var(--apple-tertiary)]">{note}</p> : null}
    </div>
  );
}

function legacyCopy(text: string): boolean {
  try {
    const el = document.createElement('textarea');
    el.value = text;
    el.setAttribute('readonly', 'readonly');
    el.style.position = 'fixed';
    el.style.opacity = '0';
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}

export function CopyButton({ text, label = '複製' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(t);
  }, [copied]);
  if (!text) return null;
  return (
    <button
      type="button"
      className="rd-btn shrink-0 !px-2 !py-[2px] !text-[10px]"
      onClick={() => {
        const done = () => setCopied(true);
        if (navigator.clipboard?.writeText) {
          navigator.clipboard.writeText(text).then(done, () => {
            if (legacyCopy(text)) done();
          });
          return;
        }
        if (legacyCopy(text)) done();
      }}
    >
      {copied ? '已複製' : label}
    </button>
  );
}

/** 全文顯示（可摺疊，不夹死正文高度）。 */
export function LongText({
  text,
  label = '全文',
  defaultOpen = false,
  mono = false,
  right,
}: {
  text: string;
  label?: string;
  defaultOpen?: boolean;
  mono?: boolean;
  right?: ReactNode;
}) {
  const trimmed = (text ?? '').trim();
  if (!trimmed) return null;
  return (
    <details open={defaultOpen} className="mt-1.5 group">
      <summary className="flex cursor-pointer list-none items-center gap-2 text-[10.5px] text-[var(--apple-tertiary)] hover:text-[var(--apple-secondary)]">
        <span className="inline-block w-3 transition-transform group-open:rotate-90">▸</span>
        <span>{label}</span>
        <span className="apple-data text-[9.5px]">{trimmed.length} 字</span>
        {right}
      </summary>
      <pre
        className={`mt-1.5 whitespace-pre-wrap break-words rounded-[7px] border border-[var(--apple-hairline)] bg-[var(--apple-canvas)] p-2.5 text-[11.5px] leading-relaxed text-[var(--apple-secondary)] ${
          mono ? 'apple-data' : ''
        }`}
      >
        {trimmed}
      </pre>
    </details>
  );
}

/** 未知結構的兜底：JSON 摺疊。 */
export function JsonBlock({
  value,
  label = '原始 JSON',
  defaultOpen = false,
}: {
  value: unknown;
  label?: string;
  defaultOpen?: boolean;
}) {
  if (value == null) return null;
  if (typeof value === 'object' && !Array.isArray(value) && Object.keys(value as object).length === 0) {
    return null;
  }
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  if (!text || !text.trim()) return null;
  return <LongText text={text} label={label} defaultOpen={defaultOpen} mono />;
}

/** 值可能為字串、陣列或物件的通用欄位內容。 */
export function AnyValue({ value }: { value: unknown }) {
  if (value == null || value === '') return <span className="text-[var(--apple-tertiary)]">—</span>;
  if (Array.isArray(value)) {
    const flat = value.map(textOf).filter(Boolean);
    if (!flat.length) return <span className="text-[var(--apple-tertiary)]">—</span>;
    if (flat.every((s) => s.length <= 40)) return <ChipList items={flat} />;
    return (
      <ul className="space-y-1">
        {flat.map((s, i) => (
          <li key={i} className="flex gap-1.5 text-[11.5px] leading-relaxed">
            <span className="text-[var(--apple-tertiary)]">{i + 1}.</span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{s}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === 'object') return <JsonBlock value={value} label="內容" />;
  return <span className="whitespace-pre-wrap break-words">{textOf(value)}</span>;
}

function textOf(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}
