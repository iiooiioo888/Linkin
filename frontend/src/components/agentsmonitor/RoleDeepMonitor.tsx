/**
 * 角色監控「模型與路由」「角色與合規」等深度資訊區塊。
 */
import { CATEGORY_LABEL, ROUTING_LABEL, TIER_LABEL, blankMetrics } from '../../lib/agentUi';
import type { RoleAgent } from '../../types';
import { RdCell } from '../RoleDeskLayout';

export function RoleDeepMonitor({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  return (
    <>
      <section className="rd-sec">
        <div className="rd-tt">模型與路由</div>
        <div className="rd-grid2">
          <RdCell label="指定模型" value={agent.preferred_model || (TIER_LABEL[agent.default_tier] ?? agent.default_tier)} />
          <RdCell label="路由" value={ROUTING_LABEL[agent.routing_strategy || ''] ?? (agent.routing_strategy || '品質')} />
          <RdCell label="故障轉移" value={String(agent.failover_models?.length ?? 0)} />
          <RdCell label="快取命中" value={String(m.cache_hits ?? 0)} />
          <RdCell label="允許工具" value={String(agent.tools_allowed?.length ?? 0)} />
          <RdCell label="人工升級" value={String(m.human_escalations ?? 0)} />
        </div>
      </section>
      <section className="rd-sec">
        <div className="rd-tt">角色與合規</div>
        <div className="rd-grid2">
          <RdCell label="狀態" value={agent.enabled === false ? '停用' : '啟用'} />
          <RdCell label="質詢層" value={agent.raho_label || '—'} />
          <RdCell label="線路" value={agent.raho_lane_label || '—'} />
          <RdCell label="分類" value={CATEGORY_LABEL[agent.category] ?? agent.category} />
          <RdCell label="語言" value={agent.language || 'zh-TW'} />
          <RdCell label="值班" value={agent.on_call ? 'On-call' : '否'} />
          <RdCell label="合規" value={agent.mainland_only ? '僅國內' : '全球'} />
          <RdCell label="日工作上限" value={agent.max_daily_items ? String(agent.max_daily_items) : '不限'} />
        </div>
      </section>
      {(agent.alerts?.length ?? 0) > 0 ? (
        <section className="rd-sec">
          <div className="rd-tt">角色告警</div>
          {agent.alerts!.map((al, i) => (
            <p key={`${al.message}-${i}`} className="text-[11px] text-[var(--console-sub)]">
              {al.level} · {al.message}
            </p>
          ))}
        </section>
      ) : null}
      {agent.system_prompt ? (
        <section className="rd-sec">
          <div className="rd-tt">角色設定摘要</div>
          <p className="line-clamp-6 whitespace-pre-wrap text-[11px] leading-relaxed text-[var(--console-sub)]">{agent.system_prompt}</p>
        </section>
      ) : null}
    </>
  );
}
