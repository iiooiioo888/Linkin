/**
 * SidePanel 實驗室導覽 sidebar。
 */
import { isLabLink, labSections, LAB_NAV_GROUPS, type LabSubTab } from '../../lib/labTabs';
import { TabBtn } from './shared';

export function LabSidebar({
  labSubTab,
  onLabSubTabChange,
}: {
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav className="sp-nav pb-3" aria-label="實驗室">
        {LAB_NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <div className="sp-group sp-group--as-written">{group.label}</div>
            {labSections(group).map((section) => (
              <div key={section.id}>
                {section.label ? <div className="sp-sub">{section.label}</div> : null}
                <div className="sp-list">
                  {section.items.map((item) =>
                    isLabLink(item) ? (
                      <a key={item.key} href={item.href} title={item.hint} className="sp-item no-underline">
                        <span className="sp-item-ic">{item.icon}</span>
                        <span className="sp-item-txt">
                          <span className="sp-item-l">{item.label}</span>
                          {item.hint ? <span className="sp-item-h">{item.hint}</span> : null}
                        </span>
                      </a>
                    ) : (
                      <TabBtn
                        key={item.key}
                        item={item}
                        active={labSubTab === item.key}
                        onClick={() => onLabSubTabChange(item.key)}
                      />
                    ),
                  )}
                </div>
              </div>
            ))}
          </div>
        ))}
      </nav>
    </div>
  );
}
