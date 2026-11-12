/**
 * RoleV3Desk — 角色監控三欄桌面（216 / 1fr / 304）。
 * 對齊 docs/design/monitor-dashboard-v3.html 與 SystemMetricsPanel 結構。
 *
 * 第十一輪重構：三欄內容與看板卡片已拆至 ./roledesk-v3/ 子元件；
 * 本檔保留三欄骨架與共用狀態（hooks 呼叫順序與資料流不變）。
 */
import { useRef, useState } from 'react';
import { useIsMobileLiteShell } from '../../hooks/useMediaQuery';
import { ConsoleThreeColumn, useScrollToSection, useSectionScrollSpy } from '../ui/ConsoleLayout';
import { CenterColumn } from './CenterColumn';
import { LeftRail } from './LeftRail';
import { RightRail } from './RightRail';
import { LEFT_SECTIONS } from './shared';
import type { RoleV3DeskProps } from './types';

export default function RoleV3Desk({
  agent,
  agents,
  rahoSnap: _rahoSnap,
  grillNodes: _grillNodes,
  l0,
  onSelectAgent,
  onOpenGrill: _onOpenGrill,
}: RoleV3DeskProps) {
  const isMobileLite = useIsMobileLiteShell();
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollTo = useScrollToSection(scrollRef);
  const activeSection = useSectionScrollSpy(LEFT_SECTIONS.map((s) => s.id), scrollRef);
  const [showDenseWidgets, setShowDenseWidgets] = useState(false);

  return (
    <ConsoleThreeColumn
      className="min-h-0 flex-1"
      liteShell={isMobileLite}
      mobileLabels={{ left: '導覽', center: '監控', right: '詳情' }}
    >
      <LeftRail
        agent={agent}
        agents={agents}
        isMobileLite={isMobileLite}
        showDenseWidgets={showDenseWidgets}
        activeSection={activeSection}
        scrollTo={scrollTo}
        onSelectAgent={onSelectAgent}
      />
      <CenterColumn
        agent={agent}
        agents={agents}
        isMobileLite={isMobileLite}
        showDenseWidgets={showDenseWidgets}
        setShowDenseWidgets={setShowDenseWidgets}
        scrollRef={scrollRef}
        onSelectAgent={onSelectAgent}
      />
      <RightRail agent={agent} l0={l0} />
    </ConsoleThreeColumn>
  );
}
