/**
 * 角色設定表單共用欄位：Field、TokenSlider、輸入樣式與選項文案。
 */
import type { ReactNode } from 'react';
import { routeDisplayName } from '../../lib/agentUi';

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-[#62666d]">{label}</span>
      {hint && <span className="ml-2 text-[10px] text-[#8a8f98]">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}

export const inputCls =
  'w-full rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2 py-1.5 text-[12px] text-[var(--console-ink)] outline-none focus:border-[color-mix(in_srgb,var(--console-accent)_60%,transparent)]';

export function tokenHint(
  model: string,
  hints?: Record<string, { max_context: number; max_output: number }>,
) {
  if (!hints || !model) return undefined;
  const bare = model.split('/').pop() || model;
  return hints[model] || hints[bare];
}

export function routeOptionLabel(route: {
  name?: string;
  provider_label?: string;
  provider?: string;
  is_default?: boolean;
  enabled?: boolean;
}): string {
  const base = routeDisplayName(route) || '未命名 API';
  const bits = [base];
  if (route.is_default) bits.push('預設');
  if (route.enabled === false) bits.push('停用');
  return bits.join(' · ');
}

export function TokenSlider({
  label,
  hint,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (n: number) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="flex items-center gap-2">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={Math.min(max, Math.max(min, value))}
          onChange={(e) => onChange(Number(e.target.value))}
          className="flex-1 accent-[var(--console-accent)]"
        />
        <input
          type="number"
          min={min}
          max={max}
          className={`${inputCls} w-24`}
          value={value}
          onChange={(e) => onChange(Number(e.target.value) || min)}
        />
      </div>
    </Field>
  );
}
