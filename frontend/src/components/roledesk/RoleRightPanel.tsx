/**
 * 右側資訊欄：L0、組織鏈、任務狀態、Token、成本、監控與事件時間線的組合。
 */

import type { AgentWorkItem, L0Snapshot, RoleAgent } from '../../types';
import type { WorkItemColumnKey } from '../../lib/agentUi';
import { OrgReportTree } from './OrgReportTree';
import { EventTimelineBlock, L0ContextBlock, RoleMonitorBlock } from './RoleMonitorBlocks';
import { CostDetailBlock, TaskStatusBlock, TokenUsageBlock } from './RoleTaskBlocks';

export function RoleRightPanel({
  agent,
  agents,
  filter,
  onFilter,
  onOpen,
  onOpenItem,
  l0,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  filter: WorkItemColumnKey;
  onFilter: (key: WorkItemColumnKey) => void;
  onOpen: (id: string) => void;
  onOpenItem?: (item: AgentWorkItem) => void;
  l0?: L0Snapshot | null;
}) {
  return (
    <aside className="rd-rp">
      <L0ContextBlock snapshot={l0} />
      <OrgReportTree agent={agent} agents={agents} onOpen={onOpen} />
      <TaskStatusBlock agent={agent} filter={filter} onFilter={onFilter} onOpenItem={onOpenItem} />
      <TokenUsageBlock agent={agent} />
      <CostDetailBlock agent={agent} />
      <RoleMonitorBlock agent={agent} />
      <EventTimelineBlock events={agent.events ?? []} />
    </aside>
  );
}
