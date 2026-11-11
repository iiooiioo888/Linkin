/**
 * 任務階段定義（標準／公司／OPC）與階段索引 helper。
 */

import { OPC_PHASES } from '../../types';

// ── 階段定義（匯出供整頁視圖复用） ──

export const STANDARD_PHASES: { key: string; label: string }[] = [
  { key: 'retrieve_memories', label: '記憶檢索' },
  { key: 'generate', label: '生成回答' },
  { key: 'evaluate', label: '自動評估' },
  { key: 'reflect', label: '反思' },
  { key: 'improve', label: '改進' },
  { key: 'done', label: '完成' },
];

export const COMPANY_PHASES: { key: string; label: string }[] = [
  { key: 'task_analysis', label: '任務分析' },
  { key: 'decompose', label: '工作拆解' },
  { key: 'execute_review', label: '執行與審查' },
  { key: 'synthesize', label: '整合交付' },
  { key: 'final_review', label: '最終審查' },
  { key: 'evaluate', label: '品質評估' },
  { key: 'done', label: '完成' },
];

export { OPC_PHASES };

export function phaseIndex(phases: { key: string }[], phase: string): number {
  return phases.findIndex((p) => p.key === phase);
}
