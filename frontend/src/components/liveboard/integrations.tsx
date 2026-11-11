/**
 * LiveBoard 外部整合／實驗室工具卡。
 */
import { isLabLink, labSections, LAB_NAV_GROUPS, type LabNavEntry, type LabSubTab } from '../../lib/labTabs';
import type { MonitorTab } from '../AppShell';
import IntegrationsStrip from '../IntegrationsStrip';
import { MonitorLinkButton, MonitorPanel } from '../ui/monitor';

export function ExternalIntegrationsCard({
  dock,
  onOpenTab,
}: {
  dock?: boolean;
  onOpenTab?: (tab: MonitorTab) => void;
}) {
  return (
    <MonitorPanel
      title="外部整合"
      accessory={
        onOpenTab ? (
          <MonitorLinkButton onClick={() => onOpenTab('integrations')} label="面板" />
        ) : (
          <MonitorLinkButton href="#/monitor/integrations" label="面板" />
        )
      }
      className={dock ? '' : 'mon-span-2'}
    >
      <IntegrationsStrip density={dock ? 'compact' : 'comfortable'} showSummary={false} showGroups={!dock} />
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-faint)]">
        MemOS 記憶 · OpenViking 分層上下文 · WeKnora 知識 · Yao 任務板 · Ouroboros 閘門 · OpenPencil 設計。預設關閉，顯式啟用。
      </p>
    </MonitorPanel>
  );
}

function labChip(
  item: LabNavEntry,
  chipClass: string,
  onOpenLab?: (sub: LabSubTab) => void,
) {
  if (isLabLink(item)) {
    return (
      <a key={item.key} href={item.href} className={chipClass} title={item.hint}>
        {item.label}
      </a>
    );
  }
  return onOpenLab ? (
    <button
      key={item.key}
      type="button"
      onClick={() => onOpenLab(item.key)}
      className={chipClass}
      title={item.upstream?.name ?? item.hint}
    >
      {item.label}
    </button>
  ) : (
    <a
      key={item.key}
      href={item.key === 'prompt' ? '#/monitor/lab' : `#/monitor/lab/${item.key}`}
      className={chipClass}
      title={item.upstream?.name ?? item.hint}
    >
      {item.label}
    </a>
  );
}

export function LabToolsCard({
  dock,
  onOpenLab,
}: {
  dock?: boolean;
  onOpenLab?: (sub: LabSubTab) => void;
}) {
  const chipClass =
    'rounded-full border border-[var(--console-line)] bg-[var(--console-card-elevated)] px-3 py-1.5 text-[11px] font-medium text-[var(--console-ink)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] hover:bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)]';

  return (
    <MonitorPanel
      title="實驗室工具"
      accessory={
        onOpenLab ? (
          <MonitorLinkButton onClick={() => onOpenLab('prompt')} label="實驗室" />
        ) : (
          <MonitorLinkButton href="#/monitor/lab" label="實驗室" />
        )
      }
      className={dock ? '' : 'mon-span-2'}
    >
      <div className="space-y-3">
        {LAB_NAV_GROUPS.map((group) => (
          <div key={group.id}>
            <p className="mb-1.5 text-[10px] font-semibold tracking-wide text-[var(--console-faint)]">{group.label}</p>
            <div className="space-y-2">
              {labSections(group).map((section) => (
                <div key={section.id}>
                  {section.label ? (
                    <p className="mb-1 text-[10px] text-[var(--console-faint)]">{section.label}</p>
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    {section.items.map((item) => labChip(item, chipClass, onOpenLab))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-faint)]">
        核心的開發組件 · 價格分析探針組件 · 整合
      </p>
    </MonitorPanel>
  );
}
