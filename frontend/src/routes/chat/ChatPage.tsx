/**
 * 對話主畫面：收發沿用既有 useChatSend／執行路徑（使用者選 simple／company，系統只建議）。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchConfig } from '../../api/client';
import ChatView from '../../components/ChatView';
import SettingsModal from '../../components/SettingsModal';
import OnboardingGuide from '../../components/onboarding/OnboardingGuide';
import { useChatSend } from '../../hooks/useChatSend';
import { useChatSessions } from '../../hooks/useChatSessions';
import type { TaskProgress } from '../../types';

export default function ChatPage() {
  const [error, setError] = useState<string | null>(null);
  const [, setRightPanelTask] = useState<TaskProgress | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);

  const refreshConfigStatus = useCallback(() => {
    fetchConfig()
      .then((cfg) => setLlmConfigured(cfg.configured))
      .catch(() => setLlmConfigured(null));
  }, []);

  useEffect(() => {
    refreshConfigStatus();
  }, [refreshConfigStatus]);

  const {
    activeSession,
    updateSession,
    handleNewSession,
    handleDecisionPending,
    handleDecisionResolved,
    handleTaskStatePatch,
  } = useChatSessions({ setError, setRightPanelTask });

  const { sending, lastQuery, sendQuery, handleRetry, handleSuggest, handleUpgrade } = useChatSend({
    activeSession,
    updateSession,
    setError,
    setRightPanelTask,
  });

  return (
    <>
      <OnboardingGuide />
      <ChatView
        messages={activeSession?.messages ?? []}
        sessionId={activeSession?.id ?? ''}
        loading={false}
        sending={sending}
        error={error}
        lastQuery={lastQuery}
        llmConfigured={llmConfigured}
        onOpenSettings={() => setSettingsOpen(true)}
        onNewSession={handleNewSession}
        onSend={(text, options) => {
          void sendQuery(text, options);
        }}
        onRetry={handleRetry}
        onDismissError={() => setError(null)}
        onSuggest={handleSuggest}
        onUpgradeToCompany={handleUpgrade}
        onDecisionPending={handleDecisionPending}
        onDecisionResolved={handleDecisionResolved}
        onTaskStatePatch={handleTaskStatePatch}
      />
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={refreshConfigStatus}
      />
    </>
  );
}
