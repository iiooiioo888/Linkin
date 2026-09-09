/**
 * ChatWorkStream — 對話旁的即時產出欄。
 * 任務進行中展示階段、草稿、角色產出與思考過程。
 */
import { useMemo } from 'react';
import type { KanbanItem, TaskEvent, TaskProgress } from '../types';
import { WORK_ITEM_COLUMNS, workItemColumnKey } from '../lib/agentUi';
import { eventBody, splitThink } from '../lib/splitThink';
import { MonitorSection } from './ChatMonitorCards';
import MarkdownBody from './media/MarkdownBody';
import { StatusColumnBoard } from './StatusColumnBoard';
import RahoDecisionBar from './RahoDecisionBar';
import { L0BiasHint } from './L0BiasHint';
import { jumpToGrillTree } from '../lib/rahoUi';
import { COMPANY_PHASES, OPC_PHASES, STANDARD_PHASES, ITEM_STATUS_META, roleLabel } from './TaskPanel';
import { eventClock } from '../lib/taskTiming';

interface ChatWorkStreamProps {
  task: TaskProgress;
  draft?: string;
  thinking?: string;
  onOpenTrace?: (taskId: string) => void;
}

function flattenItems(task: TaskProgress): Array<{ item: KanbanItem; status: string }> {
  const rows: Array<{ item: KanbanItem; status: string }> = [];
  for (const [status, items] of Object.entries(task.kanban ?? {})) {
    for (const item of items) {
      rows.push({ item, status });
    }
  }
  return rows.sort((a, b) => (b.item.updated_at ?? '').localeCompare(a.item.updated_at ?? ''));
}

function eventText(ev: TaskEvent): string {
  return eventBody(ev.data).trim();
}

export default function ChatWorkStream({ task, draft, thinking, onOpenTrace }: ChatWorkStreamProps) {
  const running = task.status === 'running' || task.status === 'pending';
  const isCompany = task.resolved_path === 'company';
  const isOPC = task.resolved_path === 'opc';
  const phases = isOPC ? OPC_PHASES : isCompany ? COMPANY_PHASES : STANDARD_PHASES;
  const phaseLabel =
    phases.find((p) => p.key === task.phase)?.label ?? (task.phase || '待命');
  const parsedDraft = splitThink(draft || task.answer || '');
  const liveText = parsedDraft.content;
  const liveThink = (thinking || parsedDraft.thinking).trim();
  const items = useMemo(() => flattenItems(task), [task]);
  const recentEvents = [...(task.events ?? [])].slice(-12).reverse();
  const pathLabel = isOPC ? 'OPC' : isCompany ? '公司協作' : '反思閉環';

  return (
    <aside className="apple-canvas hidden min-h-0 w-[300px] shrink-0 flex-col overflow-y-auto border-l border-white/[0.08] p-4 lg:flex xl:w-[340px]">
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <p className="apple-title">即時產出</p>
          <p className="mt-1 text-[10px] text-[#636366]">
            {pathLabel}
            {running ? ' · 進行中' : ` · ${task.status}`}
            {(task.created_at ?? 0) > 0 && ` · ${eventClock(task.created_at as number)} 開始`}
          </p>
        </div>
        {onOpenTrace && (
          <button
            type="button"
            onClick={() => onOpenTrace(task.task_id)}
            className="rounded-lg border border-white/[0.08] px-2 py-1 text-[10px] font-medium text-[#8E8E93] hover:border-[#0A84FF]/40 hover:text-[#64B5FF]"
          >
            軌跡
          </button>
        )}
      </div>

      <RahoDecisionBar pending={task.raho?.pending_decisions ?? []} />
      <L0BiasHint snapshot={task.raho?.l0} compact />
      {(task.raho?.trees?.length ?? 0) > 0 ? (
        <button type="button" className="l0-link mb-3" onClick={() => jumpToGrillTree()}>
          對照質詢 · {task.raho!.trees!.length} 條鏈
        </button>
      ) : null}

      <MonitorSection title="當前階段" hint={phaseLabel} badge={running ? 'LIVE' : undefined}>
        <p className="text-[12px] leading-relaxed text-[#AEAEB2]">{task.query.slice(0, 120)}</p>
      </MonitorSection>

      {liveThink && (
        <MonitorSection title="思考過程" hint={`${liveThink.length} 字`}>
          <pre className="max-h-[220px] overflow-y-auto whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-[#AEAEB2]">
            {liveThink}
          </pre>
        </MonitorSection>
      )}

      <MonitorSection title="生成內容" hint={liveText ? `${liveText.length} 字` : '等待寫入'}>
        {liveText ? (
          <div className="markdown-body max-h-[320px] overflow-y-auto text-[12px] leading-relaxed text-[#F5F5F7]">
            <MarkdownBody markdown={liveText} className="" />
          </div>
        ) : (
          <p className="py-6 text-center text-[11px] text-[#636366]">
            {running ? '模型正在生成，內容會即時出現於此' : '尚無草稿'}
          </p>
        )}
      </MonitorSection>

      {items.length > 0 && (
        <MonitorSection title="角色產出" hint={`${items.length} 項`}>
          <StatusColumnBoard
            compact
            columns={WORK_ITEM_COLUMNS.map((col) => {
              const rows = items.filter((row) => workItemColumnKey(row.status) === col.key);
              return {
                key: col.key,
                label: col.label,
                count: rows.length,
                children: rows.map(({ item, status }) => {
                  const parsed = splitThink(item.output ?? '');
                  const think = (item.thinking || parsed.thinking).trim();
                  const output = parsed.content || item.output || '';
                  const meta = ITEM_STATUS_META[status] ?? { label: status };
                  const running = col.key === 'executing';
                  return (
                    <div key={item.id} className="rd-tc">
                      <div className="rd-tc-t">
                        <span className={`rd-od ${running ? 'run' : col.key === 'done' ? 'on' : 'off'}`} />
                        <span className="rd-tc-ttl">{item.title}</span>
                      </div>
                      <div className="rd-tc-m">
                        <span className={`rd-badge ${running ? 'run' : ''}`}>{meta.label}</span>
                        {item.assignee ? <span className="rd-tc-meta">{roleLabel(item.assignee)}</span> : null}
                      </div>
                      {think && (
                        <details className="mt-1.5">
                          <summary className="cursor-pointer text-[10px] text-[#636366]">思考過程</summary>
                          <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap font-sans text-[11px] leading-relaxed text-[#8E8E93]">
                            {think}
                          </pre>
                        </details>
                      )}
                      {output ? (
                        <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-[#AEAEB2]">
                          {output}
                        </p>
                      ) : (
                        <p className="mt-1 text-[11px] text-[#636366]">{running ? '此角色尚未寫入' : '無產出'}</p>
                      )}
                    </div>
                  );
                }),
              };
            })}
          />
        </MonitorSection>
      )}

      {recentEvents.length > 0 && (
        <MonitorSection title="事件" hint="最近">
          <div className="space-y-2">
            {recentEvents.map((ev, i) => {
              const body = eventText(ev);
              return (
                <div key={`${ev.ts}-${ev.event}-${i}`} className="border-b border-white/[0.06] pb-2 last:border-0">
                  <p className="flex items-baseline justify-between gap-2 text-[11px] font-bold text-[#F5F5F7]">
                    <span className="min-w-0 truncate">{ev.event.replace(/_/g, ' ')}</span>
                    <span className="shrink-0 font-mono text-[9px] font-normal text-[#636366]">{eventClock(ev.ts)}</span>
                  </p>
                  {body && (
                    <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-[#AEAEB2]">
                      {body}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </MonitorSection>
      )}
    </aside>
  );
}
