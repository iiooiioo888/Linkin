/**
 * PlaneBadge — 平面邊界可見標籤（計算＝AI-Core／供給＝Cloud Core／資產＝只存與取）。
 */
import type { ReactNode } from 'react';

export type PlaneKind = 'ai-core' | 'cloud-core' | 'assets';

const PLANE_LABEL: Record<PlaneKind, string> = {
  'ai-core': 'AI-Core',
  'cloud-core': 'Cloud Core',
  assets: '只存與取',
};

const PLANE_HINT: Record<PlaneKind, string> = {
  'ai-core': '計算平面由 AI-Core 執行，非 Linkin 本機推理',
  'cloud-core': '供給平面由 Cloud Core 提供容量與節點',
  assets: '資產層只存與取，不決策',
};

export function planeKindForActivity(
  activity: string,
): PlaneKind | null {
  if (activity === 'compute') return 'ai-core';
  if (activity === 'supply') return 'cloud-core';
  if (activity === 'assets') return 'assets';
  return null;
}

export default function PlaneBadge({
  kind,
  className = '',
}: {
  kind: PlaneKind;
  className?: string;
}): ReactNode {
  return (
    <span
      className={`plane-badge inline-flex items-center rounded border border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-[var(--console-accent)] ${className}`}
      title={PLANE_HINT[kind]}
      data-plane={kind}
    >
      {PLANE_LABEL[kind]}
    </span>
  );
}
