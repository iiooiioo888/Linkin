/**
 * 角色監控區塊：容量／預算告警、活動熱圖、技能標籤、事件時間線與 L0 知識記憶。
 */

import type { AgentEvent, L0Snapshot, RoleAgent } from '../../types';
import { blankMetrics, fmtWhen } from '../../lib/agentUi';
import { jumpToL0Kernel } from '../../lib/rahoUi';
import { agentResourceGauges, buildActivityHeatmap } from '../../lib/monitorData';
import { ActivityHeatmap, ResourceGauges, SkillTags } from '../ui/monitor';
import { eventLabel } from './shared';

export function RoleMonitorBlock({ agent }: { agent: RoleAgent }) {
  const m = agent.metrics ?? blankMetrics();
  const handled = agent.company_tasks?.length ?? 0;
  const capPct = m.capacity_pct ?? Math.round((agent.capacity_used ?? 0) * 100);
  const heatmap = buildActivityHeatmap(
    (agent.company_tasks ?? []).map((wi) => ({
      task_id: wi.task_id,
      query: wi.query,
      strategy: '',
      resolved_path: 'company',
      status: wi.status,
      phase: wi.phase,
      score: null,
      iteration: 0,
      spent: 0,
      created_at: Math.floor(Date.now() / 1000),
      events_count: 0,
      answer_preview: '',
    })),
    agent.events ?? [],
    12,
  );
  const heatmapEmpty = heatmap.every((r) => r.every((c) => c.level === 0 && !c.error));
  const skillTags = [...(agent.tags ?? []), ...(agent.tools_allowed ?? []).slice(0, 4)];

  return (
    <div className="rd-sec space-y-3">
      <div className="rd-tt">角色監控</div>
      <ResourceGauges gauges={agentResourceGauges(agent)} size={44} />
      {(m.budget_alerts ?? 0) > 0 || capPct >= 100 ? (
        <div className="rounded border border-[var(--console-amber)]/40 bg-[var(--console-amber)]/10 px-2 py-1.5 text-[10px] text-[var(--console-amber)]">
          {capPct >= 100 ? `容量 100%（${agent.executing}/${agent.max_parallel_work}）` : null}
          {(m.budget_alerts ?? 0) > 0 ? ` · 預算告警 ${m.budget_alerts}` : null}
        </div>
      ) : null}
      <div className="rd-grid2">
        <div className="rd-cell">
          <div className="rd-cell-l">協辦任務</div>
          <div className="rd-cell-v" style={{ color: 'var(--console-blue)', fontSize: 14 }}>{handled || agent.work_items.length}</div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">本角色經手</div>
          <div className="rd-cell-v" style={{ color: 'var(--console-sub)', fontSize: 14 }}>{handled ? handled : '—'}</div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">預算告警</div>
          <div className="rd-cell-v" style={{ color: (m.budget_alerts ?? 0) > 0 ? 'var(--console-amber)' : 'var(--console-green)', fontSize: 14 }}>
            {m.budget_alerts ?? 0}
          </div>
        </div>
        <div className="rd-cell">
          <div className="rd-cell-l">錯誤</div>
          <div className="rd-cell-v" style={{ color: (m.errors ?? 0) > 0 ? 'var(--console-danger)' : 'var(--console-green)', fontSize: 14 }}>
            {m.errors ?? 0}
          </div>
        </div>
      </div>
      <ActivityHeatmap rows={heatmap} demo={heatmapEmpty} title="活動" />
      <div>
        <p className="mb-1.5 text-[9px] font-semibold text-[var(--console-faint)]">技能</p>
        <SkillTags tags={skillTags} />
      </div>
    </div>
  );
}

export function EventTimelineBlock({ events }: { events: AgentEvent[] }) {
  return (
    <div className="rd-sec">
      <div className="rd-tt">事件時間線</div>
      {events.length === 0 ? (
        <p className="py-1 text-[11px] text-[var(--console-sub)]">尚無此角色事件</p>
      ) : (
        <div className="rd-ev">
          {events.slice(0, 8).map((ev, i) => {
            const bad = ev.event.includes('error') || ev.event.includes('fail');
            return (
              <div key={`${ev.ts}-${ev.event}-${i}`} className="rd-ev-row">
                <span className={`rd-ev-dot ${bad ? 'er' : 'go'}`} />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[10.5px] text-[var(--console-sub)]">
                    {ev.title ? `${ev.title} — ${eventLabel(ev.event)}` : eventLabel(ev.event)}
                  </div>
                  <div className="apple-data text-[8.5px] text-[var(--console-sub)]">{fmtWhen(ev.ts)}</div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}


export function L0ContextBlock({ snapshot }: { snapshot?: L0Snapshot | null }) {
  const radar = snapshot?.radar;
  const pressure = Math.round((radar?.pressure ?? 0) * 100);
  const lesson = snapshot?.traces?.find((t) => t.failure_reason) ?? snapshot?.traces?.[0];
  const knowledge = snapshot?.knowledge?.[0];
  return (
    <div className="rd-sec">
      <div className="rd-tt">
        L0 知識與記憶
        <button type="button" className="rd-link" onClick={jumpToL0Kernel}>
          開核心
        </button>
      </div>
      <p className="text-[11px] leading-relaxed text-[var(--console-sub)]">
        {radar?.bias_instructions || '環境壓力正常，依規格驗收。'}
      </p>
      <p className={`mt-1 text-[10px] ${radar?.energy_save ? 'text-[var(--console-amber)]' : 'text-[var(--console-sub)]'}`}>
        壓力 {pressure}%{radar?.energy_save ? ' · 節能模式' : ''}
      </p>
      {knowledge ? <p className="mt-1 text-[10px] text-[var(--console-sub)]">知識：{knowledge.content}</p> : null}
      {lesson ? <p className="mt-1 text-[10px] text-[var(--console-sub)]">記憶：{lesson.summary}</p> : null}
    </div>
  );
}
