/**
 * SidePanel 共用樣式化小元件。
 */
import type { ConsoleNavItem } from '../../lib/monitorTabs';

export function TabBtn({
  item,
  active,
  onClick,
}: {
  item: ConsoleNavItem | { key: string; icon: string; label: string; hint?: string };
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={item.hint}
      className={`sp-item ${active ? 'on' : ''}`}
    >
      <span className="sp-item-ic">{item.icon}</span>
      <span className="sp-item-txt">
        <span className="sp-item-l">{item.label}</span>
        {item.hint ? <span className="sp-item-h">{item.hint}</span> : null}
      </span>
    </button>
  );
}
