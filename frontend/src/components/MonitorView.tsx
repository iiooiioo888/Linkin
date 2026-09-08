/**
 * MonitorView — 統一監控視圖（懶加載重模組 + Hub 推送）。
 * 分頁切換由左側 SidePanel 負責；此處僅渲染當前分頁。
 */
import { lazy, Suspense, useEffect, useState } from 'react';
import { fetchL0Kernel } from '../api/client';
import { useMonitorHub } from '../hooks/useMonitorHub';
import { buildAnimLiveFeed } from '../lib/animLive';
import { isLinkinStudioAgent } from '../lib/agentUi';
import { jumpToL0Kernel } from '../lib/rahoUi';
import { useMonitorStore } from '../stores/monitorStore';
import type { L0Snapshot, TaskProgress } from '../types';
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
const LlmOpsPanel = lazy(() => import('./LlmOpsPanel'));
const L0Panel = lazy(() => import('./L0Panel'));
const WorldConstitutionPanel = lazy(() => import('./linkin/WorldConstitutionPanel'));
const NpcManagerPanel = lazy(() => import('./linkin/NpcManagerPanel'));
const QuestPanel = lazy(() => import('./linkin/QuestPanel'));
const BuildPanel = lazy(() => import('./linkin/BuildPanel'));
const ItemPanel = lazy(() => import('./linkin/ItemPanel'));
const MinecraftBridgePanel = lazy(() => import('./linkin/MinecraftBridgePanel'));

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
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
}: {
  onOpenLab?: (sub: LabSubTab) => void;
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenTraces?: () => void;
  onOpenAgent?: (id: string) => void;
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
  const [l0, setL0] = useState<L0Snapshot | null>(null);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const next = await fetchL0Kernel();
        if (alive) setL0(next);
      } catch {
        if (alive) setL0(null);
      }
    };
    void load();
    const t = setInterval(() => void load(), 8000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

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
      {l0 ? (
        <button type="button" className="l0-live mx-5 mt-4" onClick={jumpToL0Kernel}>
          <div>
            <p>L0 態勢 · {l0.radar?.energy_save ? '節能模式' : '壓力正常'}</p>
            <span>{l0.radar?.bias_instructions || '三核待命：記憶／知識／雷達'}</span>
          </div>
          <span>壓力 {Math.round((l0.radar?.pressure ?? 0) * 100)}%</span>
        </button>
      ) : null}
      <LiveBoard
        feed={liveFeed}
        onOpenLab={onOpenLab}
        onOpenTab={onOpenTab}
        onOpenTraces={onOpenTraces}
        onOpenAgent={onOpenAgent}
      />
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

  useMonitorHub(tab !== 'lab');

  return (
    <div className="flex flex-1 flex-col overflow-hidden apple-canvas">
      <Suspense fallback={<PanelFallback />}>
        {tab === 'live' && (
          <LiveTab
            onOpenLab={(sub) => {
              onTabChange('lab');
              onLabSubTabChange(sub);
            }}
            onOpenTab={onTabChange}
            onOpenTraces={() => onOpenTrace?.('')}
            onOpenAgent={(id) => {
              onFocusAgent(id);
              onTabChange(isLinkinStudioAgent(id) ? 'studio' : 'agents');
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
          <AgentsMonitorPanel focusAgentId={focusAgentId} onFocusAgent={onFocusAgent} deskScope="console" />
        )}
        {tab === 'pipeline' && <PipelineView onGoTasks={() => onTabChange('tasks')} />}
        {tab === 'metrics' && <SystemMetricsPanel />}
        {tab === 'models' && <ModelCallPanel />}
        {tab === 'feedback' && <UserFeedbackPanel />}
        {tab === 'lab' && (
          <LabPanel activeTab={labSubTab} onTabChange={onLabSubTabChange} />
        )}
        {tab === 'ops' && <OpsPanel />}
        {tab === 'llm' && <LlmOpsPanel />}
        {tab === 'memory' && (
          <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-5 py-4 apple-canvas">
            <L0Panel />
          </div>
        )}
        {tab === 'world' && <WorldConstitutionPanel />}
        {tab === 'npcs' && <NpcManagerPanel />}
        {tab === 'quests' && <QuestPanel />}
        {tab === 'building' && <BuildPanel />}
        {tab === 'items' && <ItemPanel />}
        {tab === 'studio' && (
          <AgentsMonitorPanel focusAgentId={focusAgentId} onFocusAgent={onFocusAgent} deskScope="linkin" />
        )}
        {tab === 'minecraft' && <MinecraftBridgePanel />}
      </Suspense>
    </div>
  );
}
