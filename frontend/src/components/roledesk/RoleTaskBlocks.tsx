/**
 * 任務與成本區塊：任務狀態、Token 用量、雲資源成本拆分與共用 RdCell。
 */

import type { AgentWorkItem, RoleAgent } from '../../types';
import {
  blankMetrics,
  fmtUsd,
  itemsInColumn,
  workItemColumnKey,
  WORK_ITEM_COLUMN_COLOR,
  WORK_ITEM_COLUMNS,
  type WorkItemColumnKey,
} from '../../lib/agentUi';
import { RoleBudgetSummary } from '../RoleBudgetSummary';
import { RING, pctBar } from './shared';

export function TaskStatusBlock({
  agent,
  filter,
  onFilter,
  onOpenItem,
}: {
  agent: RoleAgent;
  filter: WorkItemColumnKey;
  onFilter: (key: WorkItemColumnKey) => void;
  onOpenItem?: (item: AgentWorkItem) => void;
}) {
  const activeKey: WorkItemColumnKey = filter;
  const preview = itemsInColumn(agent.work_items, activeKey);
  return (
    <div className="rd-sec">
      <div className="rd-tt">任務狀態</div>
      <div className="rd-sum">
        {WORK_ITEM_COLUMNS.map((col) => {
          const count = itemsInColumn(agent.work_items, col.key).length;
          return (
            <button
              key={col.key}
              type="button"
              className={`rd-card ${activeKey === col.key ? 'sel' : ''}`}
              onClick={() => onFilter(col.key)}
            >
              <div
                className="rd-num"
                style={{ color: count ? WORK_ITEM_COLUMN_COLOR[col.key] : 'var(--apple-tertiary)' }}
              >
                {count}
              </div>
              <div className="rd-lbl">{col.label}</div>
            </button>
          );
        })}
      </div>
      <div className="rd-mini">
        {preview.slice(0, 5).map((item) => {
          const col = workItemColumnKey(item.status);
          return (
          <button
            key={`${item.task_id}-${item.id}-${item.kind}`}
            type="button"
            className="rd-item"
            onClick={() => onOpenItem?.(item)}
          >
            <span className={`rd-sd ${col === 'executing' ? 'r' : col === 'done' ? 'd' : 'q'}`} />
            <span className="rd-item-name">{item.title}</span>
            <span className="rd-item-right">{fmtUsd(item.cost_usd)}</span>
          </button>
          );
        })}
        {preview.length === 0 ? <p className="py-2 text-center text-[11px] text-[var(--console-sub)]">尚無工作項</p> : null}
      </div>
    </div>
  );
}

export function TokenUsageBlock({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const tin = m.tokens_in ?? 0;
  const tout = m.tokens_out ?? 0;
  const ctx = agent.context_window || agent.max_output_tokens || 4096;
  const used = tin + tout;
  const max = Math.max(ctx, used, 1);
  const inLen = RING * (tin / max);
  const outLen = RING * (tout / max);
  return (
    <div className="rd-sec">
      <div className="rd-tt">Token 用量</div>
      <div className="rd-tk">
        <div className="rd-ring">
          <svg viewBox="0 0 40 40">
            <circle className="rd-ring-bg" cx="20" cy="20" r="15.5" />
            <circle
              cx="20"
              cy="20"
              r="15.5"
              stroke="var(--apple-blue)"
              strokeDasharray={`${inLen} ${RING}`}
              strokeDashoffset={0}
            />
            <circle
              cx="20"
              cy="20"
              r="15.5"
              stroke="var(--apple-green)"
              strokeDasharray={`${outLen} ${RING}`}
              strokeDashoffset={-inLen}
            />
          </svg>
          <div className="rd-center">
            <span className="apple-data text-[15px] font-bold leading-none">{used.toLocaleString()}</span>
            <span className="mt-0.5 text-[7.5px] text-[var(--console-sub)]">tok</span>
          </div>
        </div>
        <div className="rd-tk-brk">
          {[
            { label: 'Input', value: tin, color: 'var(--apple-blue)', max: ctx },
            { label: 'Output', value: tout, color: 'var(--apple-green)', max: ctx },
            { label: 'Context', value: ctx, color: '#bf5af2', max: ctx },
          ].map((row) => (
            <div key={row.label}>
              <div className="rd-tk-item">
                <span className="rd-tk-dot" style={{ background: row.color }} />
                <span className="rd-tk-l">{row.label}</span>
                <span className="rd-tk-v">{row.value.toLocaleString()} tok</span>
              </div>
              <div className="rd-tk-bar">
                <div className="rd-bar-f" style={{ width: `${pctBar(row.value, row.max)}%`, background: row.color }} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CostDetailBlock({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const docker = agent.docker_cost_usd ?? 0;
  const aliyun = agent.aliyun_cost_usd ?? 0;
  const api = m.api_spent_usd ?? agent.api_cost_usd ?? 0;
  const cloud = m.cloud_spent_usd ?? agent.cloud_cost_usd ?? docker + aliyun;
  const total = m.daily_spent_usd ?? agent.cost_usd ?? api + cloud;
  return (
    <div className="space-y-3">
      <RoleBudgetSummary agent={agent} />
      <div className="rd-sec">
        <div className="rd-tt">雲資源拆分</div>
        <div className="rd-grid2">
          <div className="rd-cell">
            <div className="rd-cell-l">Docker</div>
            <div className="rd-cell-v">{fmtUsd(docker)}</div>
          </div>
          <div className="rd-cell">
            <div className="rd-cell-l">阿里雲</div>
            <div className="rd-cell-v">{fmtUsd(aliyun)}</div>
          </div>
        </div>
        <div className="rd-cost-tot mt-2">
          <span className="rd-cost-tot-l">今日合計（參考）</span>
          <span className="rd-cost-tot-v">{fmtUsd(total)}</span>
        </div>
        <div className="rd-cost-note">
          <span>兩筆預算互不混算</span>
          <span>預算告警：{m.budget_alerts ?? 0}</span>
        </div>
      </div>
    </div>
  );
}

export function RdCell({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="rd-cell">
      <div className="rd-cell-l">{label}</div>
      <div className="rd-cell-v" style={{ fontSize: 14, ...(color ? { color } : {}) }}>
        {value}
      </div>
    </div>
  );
}
