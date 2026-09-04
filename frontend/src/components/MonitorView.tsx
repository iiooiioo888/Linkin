/**
 * MonitorView — 統一監控視圖（懶加載重模組 + Hub 推送）。
 * 分頁切換由左側 SidePanel 負責；此處僅渲染當前分頁。
 */
import { lazy, Suspense } from 'react';
import { useMonitorHub } from '../hooks/useMonitorHub';
import { buildAnimLiveFeed } from '../lib/animLive';
import { useMonitorStore } from '../stores/monitorStore';
import type { TaskProgress } from '../types';
import type { MonitorTab } from './AppShell';
import type { LabSubTab } from '../lib/labTabs';
import LiveBoard from './LiveBoard';
import ErrorState from './ui/ErrorState';

const AgentsMonitorPanel = lazy(() => import('./AgentsMonitorPanel'));
const TasksMonitorPanel = lazy(() => import('./TasksMonitorPanel'));
const PipelineView = lazy(() => import('./PipelineView'));
const SystemMetricsPanel = lazy(() => import('./SystemMetricsPanel'));
const ModelCallPanel = lazy(() => import('./ModelCallPanel'));
const UserFeedbackPanel = lazy(() => import('./UserFeedbackPanel'));
const LabPanel = lazy(() => import('./LabPanel'));
const OpsPanel = lazy(() => import('./OpsPanel'));
const MemoryPanel = lazy(() => import('./MemoryPanel'));
const WorldConstitutionPanel = lazy(() => import('./linkin/WorldConstitutionPanel'));
const NpcManagerPanel = lazy(() => import('./linkin/NpcManagerPanel'));
const QuestPanel = lazy(() => import('./linkin/QuestPanel'));
const BuildPanel = lazy(() => import('./linkin/BuildPanel'));
const ItemPanel = lazy(() => import('./linkin/ItemPanel'));

interface MonitorViewProps {
  onOpenTask: (task: TaskProgress) => void;
  onOpenTrace?: (taskId: string) => void;
  activeTab: MonitorTab;
  onTabChange: (tab: MonitorTab) => void;
  focusAgentId: string | null;
  onFocusAgent: (id: string | null) => void;
  focusTaskId: string | null;
  onFocusTask: (id: string | null) => void;
  labSubTab: LabSubTab;
  onLabSubTabChange: (tab: LabSubTab) => void;
}

function PanelFallback() {
  return (
    <div className="flex flex-1 items-center justify-center text-[12px] text-[#8E8E93]">
      載入模組…
    </div>
  );
}

function LiveTab({
  onOpenLab,
}: {
  onOpenLab?: (sub: LabSubTab) => void;
}) {
  const agents = useMonitorStore((s) => s.agents);
  const optimization = useMonitorStore((s) => s.optimization);
  const billing = useMonitorStore((s) => s.billing);
  const llmOps = useMonitorStore((s) => s.llmOps);
  const generatedAt = useMonitorStore((s) => s.generated_at);
  const connected = useMonitorStore((s) => s.connected);
  const error = useMonitorStore((s) => s.error);

  const liveFeed = buildAnimLiveFeed({
    agents,
    optimization,
    billing,
    llmOps,
    updatedAt: generatedAt,
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {error && (
        <div className="shrink-0 px-6 pt-4">
          <ErrorState kind="partial" message={error} compact />
        </div>
      )}
      {!connected && !error && (
        <div className="shrink-0 px-5 py-2 text-[10px] text-[#48484A]">離線資料</div>
      )}
      <LiveBoard feed={liveFeed} onOpenLab={onOpenLab} />
    </div>
  );
}

export default function MonitorView({
  onOpenTask,
  onOpenTrace,
  activeTab,
  onTabChange,
  focusAgentId,
  onFocusAgent,
  focusTaskId,
  onFocusTask,
  labSubTab,
  onLabSubTabChange,
}: MonitorViewProps) {
  const tab = activeTab;

  useMonitorHub(
    tab === 'agents' || tab === 'pipeline' || tab === 'live' || tab === 'tasks',
  );

  return (
    <div className="flex flex-1 flex-col overflow-hidden apple-canvas">
      <Suspense fallback={<PanelFallback />}>
        {tab === 'live' && (
          <LiveTab
            onOpenLab={(sub) => {
              onTabChange('lab');
              onLabSubTabChange(sub);
            }}
          />
        )}
        {tab === 'tasks' && (
          <TasksMonitorPanel
            focusTaskId={focusTaskId}
            onFocusTask={onFocusTask}
            onOpenTask={onOpenTask}
            onOpenTrace={onOpenTrace}
          />
        )}
        {tab === 'agents' && (
          <AgentsMonitorPanel focusAgentId={focusAgentId} onFocusAgent={onFocusAgent} />
        )}
        {tab === 'pipeline' && <PipelineView onGoTasks={() => onTabChange('tasks')} />}
        {tab === 'metrics' && <SystemMetricsPanel />}
        {tab === 'models' && <ModelCallPanel />}
        {tab === 'feedback' && <UserFeedbackPanel />}
        {tab === 'lab' && (
          <LabPanel activeTab={labSubTab} onTabChange={onLabSubTabChange} />
        )}
        {tab === 'ops' && <OpsPanel />}
        {tab === 'memory' && (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
            <MemoryPanel />
          </div>
        )}
        {tab === 'world' && <WorldConstitutionPanel />}
        {tab === 'npcs' && <NpcManagerPanel />}
        {tab === 'quests' && <QuestPanel />}
        {tab === 'building' && <BuildPanel />}
        {tab === 'items' && <ItemPanel />}
        {tab === 'dbpool' && <OpsPanel />}
      </Suspense>
    </div>
  );
}
