/**
 * 控制台統一三欄：隊列 / 執行中 / 已完成。
 */
import type { ReactNode } from 'react';

export function StatusColumnBoard({
  columns,
  selectedKey,
  onSelect,
  compact,
}: {
  columns: Array<{ key: string; label: string; count: number; children: ReactNode }>;
  selectedKey?: string;
  onSelect?: (key: string) => void;
  compact?: boolean;
}) {
  return (
    <div className={`rd-board ${compact ? 'rd-board--compact' : ''}`}>
      {columns.map((col) => (
        <section key={col.key} className={`rd-col ${selectedKey === col.key ? 'sel' : ''}`}>
          <button
            type="button"
            className="rd-col-h"
            onClick={() => onSelect?.(col.key)}
          >
            <span>{col.label}</span>
            <span>{col.count}</span>
          </button>
          <div className="rd-col-list">
            {col.count === 0 ? <p className="rd-col-empty">尚無{col.label}</p> : col.children}
          </div>
        </section>
      ))}
    </div>
  );
}
