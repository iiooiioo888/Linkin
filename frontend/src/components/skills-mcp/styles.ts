/**
 * 技能與 MCP 面板共用樣式常數。
 *
 * 由 SkillsMcpPanel.tsx 拆出；樣式字串集中管理，避免各區塊重複定義。
 */

import { consoleLayout } from '../ui/ConsoleLayout';

export const inputCls =
  'w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[var(--console-ink)] outline-none focus:border-[var(--console-blue)]/50';
export const btnCls =
  'rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2.5 py-1 text-[11px] text-[var(--console-sub)] hover:text-[var(--console-ink)] disabled:opacity-40';
export const btnPrimaryCls =
  'rounded-xl border border-[var(--console-blue)]/40 bg-[var(--console-blue)]/10 px-2.5 py-1 text-[11px] console-status-blue disabled:opacity-40';
export const cardCls = consoleLayout.insetCard;
