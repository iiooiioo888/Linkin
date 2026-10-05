/**
 * MonitorView — 統一監控視圖（懶加載重模組 + Hub 推送）。
 * 分頁切換由左側 SidePanel 負責；此處僅渲染當前分頁。
 */
import { lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { useMonitorHub } from '../hooks/useMonitorHub';
import { useIsMobileLiteShell } from '../hooks/useMediaQuery';
import { isMobileDesktopOnlyPanel } from '../lib/mobileShell';
import { buildAnimLiveFeed } from '../lib/animLive';
import { isLinkinStudioAgent } from '../lib/agentUi';
import { useMonitorStore } from '../stores/monitorStore';
import type { ChatMessage, TaskProgress } from '../types';
import type { MonitorTab } from './AppShell';
import type { LabSubTab } from '../lib/labTabs';
import { moduleIdForTab } from '../lib/worldModules';
import ModuleWorkspace from '../modules/ModuleWorkspace';
import LiveBoard from './LiveBoard';
import ErrorState from './ui/ErrorState';
import { MobileLiteGate } from './ui/MobileLiteGate';
import { PanelShell } from './ui/ConsoleLayout';

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
const SkillsMcpPanel = lazy(() => import('./SkillsMcpPanel'));
const IntegrationsPanel = lazy(() => import('./IntegrationsPanel'));
const ContextPanel = lazy(() => import('./ContextPanel'));
interface MonitorViewProps {
  onOpenTask: (task: TaskProgress) => void;
  onOpenTrace?: (taskId: string) => void;
  messages?: ChatMessage[];
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
    <div className="flex h-full min-h-0 flex-1 items-center justify-center text-[12px] text-[var(--console-sub)]">
      載入模組…
    </div>
  );
}

function LiveTab({
  messages = [],
  onOpenLab,
  onOpenTab,
  onOpenTraces,
  onOpenAgent,
  liteShell,
}: {
  messages?: ChatMessage[];
  onOpenLab?: (sub: LabSubTab) => void;
  onOpenTab?: (tab: MonitorTab) => void;
  onOpenTraces?: () => void;
  onOpenAgent?: (id: string) => void;
  liteShell?: boolean;
}) {
  const agents = useMonitorStore((s) => s.agents);
  const optimization = useMonitorStore((s) => s.optimization);
  const billing = useMonitorStore((s) => s.billing);
  const llmOps = useMonitorStore((s) => s.llmOps);
  const generatedAt = useMonitorStore((s) => s.generated_at);
  const error = useMonitorStore((s) => s.error);

  const dashboard = useMonitorStore((s) => s.dashboard);
  const backgroundPhase = dashboard?.tasks?.find(
    (t) => t.status === 'running' || t.status === 'pending',
  )?.phase;

  const liveFeed = buildAnimLiveFeed({
    agents,
    optimization,
    billing,
    llmOps,
    messages,
    updatedAt: generatedAt,
  });
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {error && (
        <div className="shrink-0 px-6 pt-4">
          <ErrorState kind="partial" message={error} compact />
        </div>
      )}
      <LiveBoard
        feed={liveFeed}
        backgroundPhase={backgroundPhase}
        liteShell={liteShell}
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
  messages = [],
  activeTab,
  onTabChange,
  focusAgentId,
  onFocusAgent,
  focusTaskId,
  onFocusTask,
  labSubTab,
  onLabSubTabChange,
}: MonitorViewProps) {
  const { t } = useTranslation();
  const tab = activeTab;
  const moduleId = moduleIdForTab(tab);
  const isMobileLite = useIsMobileLiteShell();

  useMonitorHub(tab !== 'lab');

  if (moduleId) {
    return (
      <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
        <ModuleWorkspace
          moduleId={moduleId}
          page={tab}
          focusAgentId={focusAgentId}
          onFocusAgent={onFocusAgent}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
      <Suspense fallback={<PanelFallback />}>
        <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
        {tab === 'live' && (
          <LiveTab
            messages={messages}
            liteShell={isMobileLite}
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
            liteShell={isMobileLite}
            focusTaskId={focusTaskId}
            onFocusTask={onFocusTask}
            onOpenTask={onOpenTask}
            onOpenTrace={onOpenTrace}
          />
        )}
        {tab === 'agents' && (
          <AgentsMonitorPanel focusAgentId={focusAgentId} onFocusAgent={onFocusAgent} deskScope="console" />
        )}
        {tab === 'pipeline' && (
          <MobileLiteGate
            gated={isMobileDesktopOnlyPanel('pipeline')}
            summary={<p className="text-[12px] text-[var(--console-sub)]">{t('mobileShell.tasksSummary')}</p>}
          >
            <PipelineView messages={messages} onGoTasks={() => onTabChange('tasks')} />
          </MobileLiteGate>
        )}
        {tab === 'metrics' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('metrics')}>
            <SystemMetricsPanel />
          </MobileLiteGate>
        )}
        {tab === 'models' && <ModelCallPanel />}
        {tab === 'feedback' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('feedback')}>
            <UserFeedbackPanel />
          </MobileLiteGate>
        )}
        {tab === 'lab' && (
          <MobileLiteGate
            gated={isMobileLite}
            summary={<p className="text-[12px] text-[var(--console-sub)]">{t('mobileShell.moreNote')}</p>}
          >
            <LabPanel activeTab={labSubTab} onTabChange={onLabSubTabChange} />
          </MobileLiteGate>
        )}
        {tab === 'ops' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('ops')}>
            <OpsPanel />
          </MobileLiteGate>
        )}
        {tab === 'llm' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('llm')}>
            <LlmOpsPanel />
          </MobileLiteGate>
        )}
        {tab === 'memory' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('memory')}>
            <PanelShell>
              <L0Panel />
            </PanelShell>
          </MobileLiteGate>
        )}
        {tab === 'context' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('context')}>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="shrink-0 border-b border-white/[0.06] bg-[color-mix(in_srgb,var(--console-card)_80%,transparent)] px-6 py-3">
                <p className="text-[12px] text-[var(--console-sub)]">
                  Context 主表面在<strong className="mx-1 text-[var(--console-ink)]">對話底部詳細區</strong>
                  （輸入 <code className="text-[11px] text-[var(--console-accent)]">/context</code>）。此處為控制台完整鏡像。
                </p>
                <button
                  type="button"
                  className="mt-1.5 rounded-lg border border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-2.5 py-1 text-[11px] font-medium text-[var(--console-accent)] hover:bg-[color-mix(in_srgb,var(--console-accent)_18%,transparent)]"
                  onClick={() => {
                    void import('../lib/contextUi').then(({ openChatContextDetail }) => {
                      openChatContextDetail(focusTaskId);
                    });
                  }}
                >
                  開啟對話詳細區 →
                </button>
              </div>
              <ContextPanel taskId={focusTaskId} />
            </div>
          </MobileLiteGate>
        )}
        {tab === 'integrations' && (
          <MobileLiteGate gated={isMobileDesktopOnlyPanel('integrations')}>
            <IntegrationsPanel />
          </MobileLiteGate>
        )}
        {tab === 'skills' && (
          <MobileLiteGate
            gated={isMobileDesktopOnlyPanel('skills')}
            summary={<p className="text-[12px] text-[var(--console-sub)]">{t('mobileShell.skillsSummary')}</p>}
          >
            <SkillsMcpPanel />
          </MobileLiteGate>
        )}
        </div>
      </Suspense>
    </div>
  );
}
