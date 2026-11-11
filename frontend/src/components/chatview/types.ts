/**
 * ChatView 對外 props 型別。
 */
import type { ChatMessage, TaskProgress } from '../../types';
import type { SendOptions } from '../InputBar';

export interface ChatViewProps {
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
  onDecisionPending?: (hasPending: boolean) => void;
  onDecisionResolved?: (decisionId?: string) => void;
  onTaskStatePatch?: (taskId: string, patch: Partial<TaskProgress> | TaskProgress) => void;
}
