/**
 * 02 任務分析 — 任務經理看到的目標。
 */
import type { TaskProgress } from '../../types';
import { Card, EmptyState, SectionHead, SubHead } from './parts';

export default function RequirementSection({ task }: { task: TaskProgress }) {
  const brief = (task.options?.semantic_brief || task.query || '').trim();

  return (
    <>
      <SectionHead index={2} title="任務分析" hint="由任務經理分析目標、里程碑與成敗標準" />
      <SubHead>任務目標</SubHead>
      {brief ? (
        <Card>
          <p className="whitespace-pre-wrap break-words text-[12px] leading-relaxed text-[var(--apple-label)]">
            {brief}
          </p>
        </Card>
      ) : (
        <EmptyState title="尚無任務目標" note="這筆任務沒有可顯示的分析原文。" />
      )}
    </>
  );
}
