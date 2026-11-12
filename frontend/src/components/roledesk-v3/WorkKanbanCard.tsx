/**
 * 看板單一工作項卡片（TaskPriorityCard 包裝，展開顯示描述與輸出）。
 */

import { fmtUsd, fmtWhen } from '../../lib/agentUi';
import { workItemPriority } from '../../lib/monitorData';
import type { AgentWorkItem } from '../../types';
import { ITEM_STATUS_META } from '../TaskPanel';
import { TaskPriorityCard } from '../ui/monitor';

export function WorkKanbanCard({
  item,
  expanded,
  onToggle,
}: {
  item: AgentWorkItem;
  expanded?: boolean;
  onToggle?: () => void;
}) {
  const st = ITEM_STATUS_META[item.status] ?? { label: item.status, cls: '' };
  const shortId = (item.task_id || item.id || '').replace(/^.*[#-]/, '').slice(-4) || item.id.slice(0, 4);
  const priority = workItemPriority(item);
  return (
    <TaskPriorityCard
      priority={priority}
      title={item.title}
      active={expanded}
      onClick={onToggle}
      meta={
        <>
          <span>{st.label}</span>
          <span>#{shortId}</span>
          <span>{fmtWhen(item.updated_at)}</span>
          <span>{fmtUsd(item.cost_usd)}</span>
        </>
      }
    >
      {expanded ? (
        <div className="mt-1 space-y-1 border-t border-[var(--console-line)] pt-1.5">
          {item.description ? (
            <p className="text-[10px] leading-relaxed text-[var(--console-sub)]">{item.description}</p>
          ) : null}
          {item.output_preview ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[var(--console-bg)] px-2 py-1 font-mono text-[9px] text-[var(--console-sub)]">
              {item.output_preview}
            </pre>
          ) : null}
        </div>
      ) : null}
    </TaskPriorityCard>
  );
}
