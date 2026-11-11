/**
 * 角色監控「角色專屬」區塊：依角色身分顯示不同指標格與快捷動作。
 */
import { blankMetrics, isQuantDeskRole } from '../../lib/agentUi';
import type { RoleAgent } from '../../types';
import { RdCell } from '../RoleDeskLayout';

function ExtraGrid({ cells }: { cells: Array<{ label: string; value: string; color?: string }> }) {
  return (
    <div className="rd-grid2">
      {cells.map((c) => (
        <RdCell key={c.label} label={c.label} value={c.value} color={c.color} />
      ))}
    </div>
  );
}

export function RoleMonitorExtras({ agent, onOpenQuant }: { agent: RoleAgent; onOpenQuant?: () => void }) {
  const m = agent.metrics ?? blankMetrics();
  if (isQuantDeskRole(agent.id)) {
    return (
      <div className="space-y-2">
        <ExtraGrid
          cells={[
            { label: '工具呼叫', value: String(m.tool_calls) },
            { label: '可回測', value: '29' },
            { label: '策略目錄', value: '300+' },
            { label: '完成', value: String(agent.done) },
          ]}
        />
        <button type="button" className="rd-btn inline-flex text-[11px] text-[var(--console-accent)]" onClick={onOpenQuant}>
          開啟回測策略庫
        </button>
      </div>
    );
  }
  if (agent.id === 'constitutional_inspector') {
    return (
      <ExtraGrid
        cells={[
          { label: '簽核通過', value: String(m.review_pass) },
          { label: '退回重做', value: String(m.review_rework) },
          { label: '向上呈報', value: String(m.human_escalations) },
          { label: '線路', value: agent.raho_lane_label || '獨立審查' },
        ]}
      />
    );
  }
  if (agent.id === 'reviewer') {
    return (
      <ExtraGrid
        cells={[
          { label: '通過', value: String(m.review_pass) },
          { label: '退回', value: String(m.review_rework) },
          { label: '強制完成', value: String(m.review_force) },
        ]}
      />
    );
  }
  if (agent.id === 'manager') {
    return (
      <ExtraGrid
        cells={[
          { label: '協調任務', value: String(agent.company_tasks.length) },
          { label: '預算告警', value: String(m.budget_alerts) },
          { label: '被質詢率', value: `${Math.round((m.grill_rate ?? 0) * 100)}%` },
          { label: '決策清晰', value: `${Math.round((m.decision_clarity ?? 1) * 100)}%` },
          { label: 'RAHO 職級', value: m.demoted ? '已降級' : m.raho_rank === 'watch' ? '觀察' : '正常' },
        ]}
      />
    );
  }
  if (agent.id === 'synthesizer') {
    const outputs = agent.work_items.filter((i) => i.kind === 'synthesize' && i.output_preview);
    return (
      <div className="rd-cell">
        <div className="rd-cell-l">最近整合產出</div>
        {outputs.length === 0 ? (
          <p className="mt-1 text-[11px] text-[var(--console-sub)]">尚無整合結果</p>
        ) : (
          outputs.slice(0, 2).map((item) => (
            <p key={`${item.task_id}-${item.id}`} className="mt-1 line-clamp-3 text-[11px] text-[var(--console-sub)]">
              {item.output_preview}
            </p>
          ))
        )}
      </div>
    );
  }
  if (agent.id === 'coordinator') {
    return (
      <ExtraGrid
        cells={[
          { label: '阻塞項', value: String(agent.blocked) },
          { label: '工具呼叫', value: String(m.tool_calls) },
        ]}
      />
    );
  }
  return (
    <ExtraGrid
      cells={[
        { label: '工具呼叫', value: String(m.tool_calls) },
        { label: '錯誤', value: String(m.errors), color: m.errors ? 'var(--apple-red)' : 'var(--apple-green)' },
        { label: '被質詢', value: `${Math.round((m.grill_rate ?? 0) * 100)}%` },
        { label: '完成', value: String(agent.done) },
      ]}
    />
  );
}
