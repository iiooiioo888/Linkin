/**
 * RoleTasksPanel — 角色工作台的「任務列表」頁籤。
 *
 * 把該角色參與的公司任務與工作項彙整成可檢閱清單：
 * - 公司任務卡（狀態/階段/查詢，點擊開任務詳情整頁）
 * - 工作項依任務分組（kind/狀態/標題/審查輪次）
 * - 頂部摘要條（各欄計數 + 進行中任務數）
 */
import { useMemo } from 'react';
import type { AgentWorkItem, RoleAgent } from '../types';
import { itemsInColumn, WORK_ITEM_COLUMNS, type WorkItemColumnKey } from '../lib/agentUi';
import { STATUS_META } from './taskdetail/labels';

const KIND_LABEL: Record<string, string> = {
  execute: '執行',
  assigned: '執行',
  review: '審查',
  rework: '重修',
  coordinate: '協調',
  decompose: '拆解',
  synthesize: '整合',
  final_review: '終審',
  inspect: '驗收',
};

function statusChip(status: string): { label: string; tone: string } {
  if (!status || status === 'unknown') return { label: '已歸檔', tone: 'var(--apple-gray)' };
  return STATUS_META[status] ?? { label: status, tone: 'var(--apple-gray)' };
}

function itemStatusTone(status: string): string {
  const col = WORK_ITEM_COLUMNS.find((c) => (c.statuses as readonly string[]).includes(status));
  if (!col) return 'var(--apple-gray)';
  const map: Record<WorkItemColumnKey, string> = {
    queue: 'var(--apple-gray)',
    executing: 'var(--apple-orange)',
    done: 'var(--apple-green)',
  };
  return map[col.key];
}

export default function RoleTasksPanel({
  agent,
  onOpenTask,
}: {
  agent: RoleAgent;
  onOpenTask: (taskId: string) => void;
}) {
  const companyTasks = agent.company_tasks ?? [];
  const workItems = agent.work_items ?? [];

  const byTask = useMemo(() => {
    const map = new Map<string, AgentWorkItem[]>();
    for (const item of workItems) {
      const key = item.task_id || '（無任務）';
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(item);
    }
    return [...map.entries()];
  }, [workItems]);

  const runningTasks = companyTasks.filter((t) => t.status === 'running' || t.status === 'pending');

  return (
    <div className="rtl">
      <div className="rtl-sum">
        {WORK_ITEM_COLUMNS.map((col) => {
          const count = itemsInColumn(workItems, col.key).length;
          return (
            <div key={col.key} className="rtl-sum-c">
              <span className="rtl-sum-n" style={{ color: count ? itemStatusTone(col.statuses[0]) : 'var(--apple-tertiary)' }}>
                {count}
              </span>
              <span className="rtl-sum-l">{col.label}</span>
            </div>
          );
        })}
        <div className="rtl-sum-c">
          <span className="rtl-sum-n" style={{ color: runningTasks.length ? 'var(--apple-orange)' : 'var(--apple-tertiary)' }}>
            {runningTasks.length}
          </span>
          <span className="rtl-sum-l">進行中任務</span>
        </div>
        <div className="rtl-sum-c">
          <span className="rtl-sum-n">{companyTasks.length}</span>
          <span className="rtl-sum-l">公司任務</span>
        </div>
      </div>

      <section className="rtl-sec">
        <div className="rtl-tt">公司任務（{companyTasks.length}）</div>
        {companyTasks.length === 0 ? (
          <p className="rtl-empty">此角色尚未參與任何公司任務。派一個公司模式任務後會出現在這裡。</p>
        ) : (
          <div className="rtl-grid">
            {companyTasks.map((t) => {
              const chip = statusChip(t.status);
              return (
                <button key={t.task_id} type="button" className="rtl-card" onClick={() => onOpenTask(t.task_id)}>
                  <div className="rtl-card-h">
                    <span className="rtl-id">#{t.task_id.slice(-6)}</span>
                    <span className="rtl-chip" style={{ color: chip.tone, borderColor: chip.tone }}>
                      {chip.label}
                    </span>
                  </div>
                  <p className="rtl-q">{t.query === t.task_id ? '（無標題歷史任務）' : t.query}</p>
                  <p className="rtl-meta">階段：{t.phase || '—'}</p>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="rtl-sec">
        <div className="rtl-tt">工作項依任務分組（{byTask.length} 組 / {workItems.length} 項）</div>
        {byTask.length === 0 ? (
          <p className="rtl-empty">目前沒有工作項。</p>
        ) : (
          byTask.map(([taskId, items]) => {
            const counts = items.reduce<Record<string, number>>((acc, it) => {
              acc[it.status] = (acc[it.status] ?? 0) + 1;
              return acc;
            }, {});
            const rawQuery =
              companyTasks.find((t) => t.task_id === taskId)?.query ||
              items[0]?.task_query ||
              '';
            const groupQuery = rawQuery && rawQuery !== taskId ? rawQuery : '';
            return (
              <div key={taskId} className="rtl-group">
                <div className="rtl-group-h">
                  <button type="button" className="rtl-group-id" onClick={() => onOpenTask(taskId)}>
                    #{taskId.slice(-6)}
                  </button>
                  {groupQuery ? <span className="rtl-group-q">{groupQuery}</span> : null}
                  <span className="rtl-group-n">{items.length} 項</span>
                  <span className="rtl-group-c">
                    {Object.entries(counts).map(([st, n]) => (
                      <span key={st} style={{ color: itemStatusTone(st) }}>
                        {st}×{n}
                      </span>
                    ))}
                  </span>
                </div>
                <div className="rtl-rows">
                  {items.map((item) => (
                    <div key={`${item.task_id}-${item.id}-${item.kind}`} className="rtl-row">
                      <span className="rtl-dot" style={{ background: itemStatusTone(item.status) }} />
                      <span className="rtl-kind">{KIND_LABEL[item.kind] ?? item.kind}</span>
                      <span className="rtl-title">{item.title}</span>
                      {item.feedback?.length ? <span className="rtl-round">回饋 {item.feedback.length}</span> : null}
                      {item.cost_usd ? <span className="rtl-round">${item.cost_usd.toFixed(3)}</span> : null}
                      <span className="rtl-st" style={{ color: itemStatusTone(item.status) }}>{item.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })
        )}
      </section>
    </div>
  );
}
