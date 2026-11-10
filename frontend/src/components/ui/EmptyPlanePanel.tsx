/**
 * Phase1 空殼頁 — 後端未開通前誠實空態＋平面說明。
 */
import PlaneBadge, { type PlaneKind } from './PlaneBadge';
import { PanelShell } from './ConsoleLayout';

const COPY: Record<
  string,
  { title: string; body: string; plane?: PlaneKind }
> = {
  approvals: {
    title: '審批佇列',
    body: '審批尚未開通（A2 前）。此處僅殼層占位，不會假裝可點過。',
  },
  exec: {
    title: '執行環境',
    body: '沙箱／Exec 狀態由 AI-Core 提供。目前無資料來源，顯示誠實空態。',
    plane: 'ai-core',
  },
  quota: {
    title: '容量與配額',
    body: '配額帳本由 Cloud Core 供給。目前無資料來源，顯示誠實空態。',
    plane: 'cloud-core',
  },
  health: {
    title: '節點健康',
    body: '節點健康由 Cloud Core 供給。目前無專用探針，顯示誠實空態。',
    plane: 'cloud-core',
  },
};

export default function EmptyPlanePanel({ tab }: { tab: string }) {
  const meta = COPY[tab] ?? {
    title: tab,
    body: '此頁尚未接入資料。',
  };
  return (
    <PanelShell constrained>
      <div className="flex min-h-[40vh] flex-col items-start justify-center gap-3 py-10">
        <div className="flex items-center gap-2">
          <h1 className="text-[18px] font-semibold text-[var(--console-ink)]">{meta.title}</h1>
          {meta.plane ? <PlaneBadge kind={meta.plane} /> : null}
        </div>
        <p className="max-w-md text-[13px] leading-relaxed text-[var(--console-sub)]">{meta.body}</p>
        <p className="text-[11px] text-[var(--console-faint)]">未接入 · 非 0% 假裝</p>
      </div>
    </PanelShell>
  );
}
