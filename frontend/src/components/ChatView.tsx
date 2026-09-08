/**
 * ChatView — 對話工作台：訊息流 + 任務即時產出。
 */
import type { ChatMessage } from '../types';
import InputBar from './InputBar';
import type { SendOptions } from './InputBar';
import ChatWorkStream from './ChatWorkStream';
import MessageList from './MessageList';
import ErrorState from './ui/ErrorState';

interface ChatViewProps {
  messages: ChatMessage[];
  sessionId: string;
  loading: boolean;
  sending: boolean;
  error: string | null;
  lastQuery: string | null;
  llmConfigured?: boolean | null;
  onOpenSettings?: () => void;
  onSend: (text: string, options: SendOptions) => void;
  onRetry: () => void;
  onDismissError: () => void;
  onOpenTask: (messageId: string) => void;
  onOpenTrace?: (taskId: string) => void;
  onSuggest: (text: string, company: boolean) => void;
  onGrillAnswer?: (messageId: string, answer: string, forceLock?: boolean) => void;
  onBattlePick?: (messageId: string, choice: string) => void;
}

function activeTaskMessage(messages: ChatMessage[]) {
  return (
    [...messages].reverse().find(
      (m) =>
        m.streaming ||
        m.taskState?.status === 'running' ||
        m.taskState?.status === 'pending',
    ) ?? null
  );
}

export default function ChatView({
  messages,
  sessionId,
  loading,
  sending,
  error,
  lastQuery,
  llmConfigured,
  onOpenSettings,
  onSend,
  onRetry,
  onDismissError,
  onOpenTask,
  onOpenTrace,
  onSuggest,
  onGrillAnswer,
  onBattlePick,
}: ChatViewProps) {
  const live = activeTaskMessage(messages);
  const showStream = Boolean(
    live?.taskState || live?.streaming || live?.thinking || live?.content,
  );
  const grilling = messages.some((m) => Boolean(m.grill && !m.grill.locked && !m.grill.terminated));
  const waitingBattle = messages.some(
    (m) => m.battle?.status === 'ESCALATE_TO_USER' && m.battle.waiting_for_user_decision,
  );

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {llmConfigured === false && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#FF9F0A]/20 bg-[#FF9F0A]/8 px-4 py-2 sm:px-6">
            <p className="text-[12px] text-[#FF9F0A]">尚未配置 API。請先加入千問／DeepSeek／Kimi／OpenRouter。</p>
            {onOpenSettings && (
              <button
                type="button"
                onClick={onOpenSettings}
                className="shrink-0 rounded-lg bg-[#FF9F0A]/15 px-2.5 py-1 text-[11px] font-medium text-[#FF9F0A] hover:bg-[#FF9F0A]/25"
              >
                加入 API
              </button>
            )}
          </div>
        )}
        {error && (
          <div className="shrink-0 px-4 pt-3 sm:px-6">
            <ErrorState
              kind={error.includes('OPC') || error.includes('護欄') ? 'opc_guard' : 'llm'}
              message={error}
              compact
              onRetry={lastQuery ? onRetry : undefined}
              onDismiss={onDismissError}
            />
          </div>
        )}

        <MessageList
          messages={messages}
          sessionId={sessionId}
          loading={loading}
          onOpenTask={onOpenTask}
          onOpenTrace={onOpenTrace}
          onSuggest={onSuggest}
          sending={sending}
          onGrillAnswer={onGrillAnswer}
          onBattlePick={onBattlePick}
        />
        <InputBar disabled={sending || grilling || waitingBattle} onSend={onSend} />
      </div>
      {showStream && live && (
        <ChatWorkStream
          task={
            live.taskState ?? {
              task_id: live.taskId ?? live.id,
              status: live.streaming ? 'running' : 'pending',
              strategy: live.executionStrategy ?? 'auto',
              resolved_path: '',
              query: lastQuery ?? '',
              template: '',
              phase: live.streamPhase ?? '',
              events: [],
              kanban: {},
              budget: {},
              answer: live.content,
              score: null,
              iteration: 0,
              error: '',
            }
          }
          draft={live.content}
          thinking={live.thinking}
          onOpenTrace={onOpenTrace}
        />
      )}
    </div>
  );
}
