/**
 * 公司模式子項三欄看板（隊列／執行中／已完成）。
 */

import { WORK_ITEM_COLUMNS, workItemColumnKey } from '../../lib/agentUi';
import { StatusColumnBoard } from '../StatusColumnBoard';
import { ITEM_STATUS_META, roleLabel } from './roleMeta';
import type { RoleWorkGroup } from './types';

export function KanbanBoard({ roleGroups }: { roleGroups: RoleWorkGroup[] }) {
  return (
        <div className="mt-2.5">
          <StatusColumnBoard
            compact
            columns={WORK_ITEM_COLUMNS.map((col) => {
              const entries = roleGroups
                .flatMap((g) => g.entries.map((e) => ({ ...e, role: g.role })))
                .filter((e) => workItemColumnKey(e.status) === col.key);
              return {
                key: col.key,
                label: col.label,
                count: entries.length,
                children: entries.map(({ status, item, role }) => {
                  const meta = ITEM_STATUS_META[status] ?? { label: status, cls: 'bg-gray-700/60 text-[var(--console-sub)]' };
                  const running = col.key === 'executing';
                  return (
                    <div key={item.id} className="rd-tc">
                      <div className="rd-tc-t">
                        <span className={`rd-od ${running ? 'run' : col.key === 'done' ? 'on' : 'off'}`} />
                        <span className="rd-tc-ttl">{item.title}</span>
                      </div>
                      <div className="rd-tc-m">
                        <span className={`rd-badge ${running ? 'run' : ''}`}>{meta.label}</span>
                        <span className="rd-tc-meta">{roleLabel(role)}</span>
                      </div>
                      {item.thinking?.trim() && (
                        <details className="mt-1.5">
                          <summary className="cursor-pointer text-[10px] text-[var(--console-faint)]">思考過程</summary>
                          <pre className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap font-sans text-[11px] leading-relaxed text-[var(--console-sub)]">
                            {item.thinking}
                          </pre>
                        </details>
                      )}
                      {item.output?.trim() && (
                        <p className="mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-[var(--console-sub)]">
                          {item.output}
                        </p>
                      )}
                    </div>
                  );
                }),
              };
            })}
          />
        </div>
  );
}
