/**
 * 03 工作拆解 — 任務經理分解後的執行計劃。
 */
import type { TaskProgress } from '../../types';
import {
  EmptyState,
  Field,
  FieldGrid,
  SectionHead,
  SubHead,
} from './parts';
import { planOf, textField } from './narrow';

export default function PlanSection({ task }: { task: TaskProgress }) {
  const plan = planOf(task);
  const execPlan = textField(plan?.execution_plan);

  return (
    <>
      <SectionHead
        index={3}
        title="工作拆解"
        hint="任務經理拆出的子工作與執行計劃"
        right={
          plan?.subtask_count != null ? (
            <span className="apple-data">{plan.subtask_count} 個子工作項</span>
          ) : null
        }
      />

      <SubHead>分解計劃</SubHead>
      {plan ? (
        <FieldGrid>
          <Field label="子工作項數" value={plan.subtask_count ?? '—'} />
          <Field label="拆解策略" value={plan.strategy} />
          <Field
            label="執行計劃"
            wide
            value={
              execPlan ? (
                <span className="whitespace-pre-wrap break-words">{execPlan}</span>
              ) : null
            }
          />
        </FieldGrid>
      ) : (
        <EmptyState title="尚無分解記錄" note="任務經理尚未完成工作拆解。" />
      )}
    </>
  );
}
