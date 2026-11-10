/**
 * 送出聊天：SSE 串流、公司任務建立與任務進度監聽綁定、重試與快捷建議。
 *
 * sendQuery 本體自 App.tsx 原樣搬入（邏輯與 dependency array 不變）；
 * 任務建立後的 WebSocket／輪詢監聽交由 useTaskProgressStream。
 */
import { useCallback, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { useTranslation } from 'react-i18next';
import { createTask, sendChatStream } from '../api/client';
import type { ChatBillingFootnote } from '../api/client';
import { formatChatBillingFootnote, requestBillingRefresh } from '../lib/billingUi';
import { resolveRoutingPreviewForSend, usesTaskWorkspace } from '../lib/routingPreview';
import { splitThink } from '../lib/splitThink';
import { useTaskProgressStream } from './useTaskProgressStream';
import type { SendOptions } from '../components/InputBar';
import type { ChatMessage, ChatSession, RoutingPreview, TaskOptions, TaskProgress } from '../types';

export interface UseChatSendOptions {
  activeSession: ChatSession | undefined;
  updateSession: (id: string, updater: (s: ChatSession) => ChatSession) => void;
  setError: Dispatch<SetStateAction<string | null>>;
  setRightPanelTask: Dispatch<SetStateAction<TaskProgress | null>>;
}

export interface UseChatSendResult {
  sending: boolean;
  lastQuery: string | null;
  sendQuery: (query: string, options: SendOptions) => Promise<void>;
  handleRetry: () => void;
  handleSuggest: (text: string, company: boolean) => void;
}

export function useChatSend({
  activeSession,
  updateSession,
  setError,
  setRightPanelTask,
}: UseChatSendOptions): UseChatSendResult {
  const { i18n } = useTranslation();

  // ── 发送状态 ──
  const [sending, setSending] = useState(false);
  const [lastQuery, setLastQuery] = useState<string | null>(null);

  const { startTaskProgressStream } = useTaskProgressStream();

  // ── 发送消息 ──
  const sendQuery = useCallback(
    async (query: string, options: SendOptions) => {
      if (!activeSession) return;
      const sessionId = activeSession.id;
      setError(null);
      setLastQuery(query);
      setSending(true);

      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: query,
        timestamp: Date.now(),
        executionStrategy: options.executionStrategy,
      };
      const assistantId = crypto.randomUUID();
      const placeholder: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        streaming: true,
        executionStrategy: options.executionStrategy,
      };

      updateSession(sessionId, (s) => ({
        ...s,
        title: s.title || query.slice(0, 40),
        updatedAt: Date.now(),
        messages: [...s.messages, userMsg, placeholder],
      }));

      let workQuery = query;
      let semanticLock: Record<string, unknown> = {};
      let precomputedPlanner: Record<string, unknown> | undefined =
        options.taskOptions?.precomputed_planner as Record<string, unknown> | undefined;

      const patchAssistantRouting = (preview: RoutingPreview) => {
        updateSession(sessionId, (s) => ({
          ...s,
          updatedAt: Date.now(),
          messages: s.messages.map((m) =>
            m.id === assistantId
              ? { ...m, meta: { ...m.meta, routingPreview: preview } }
              : m,
          ),
        }));
      };

      let routingPreview = await resolveRoutingPreviewForSend({
        query,
        mode: options.executionStrategy,
        companyTemplate: options.companyTemplate,
        snapshot: options.routingPreviewSnapshot,
      });
      if (routingPreview) {
        patchAssistantRouting(routingPreview);
      }

      if (options.taskOptions?.semantic_brief || options.taskOptions?.auditor_ticket) {
        semanticLock = {
          locked: true,
          locked_brief: options.taskOptions.semantic_brief || workQuery,
          ticket: options.taskOptions.auditor_ticket ?? null,
        };
      }

      // ── 簡單／minecraft_ops 走 SSE；公司任務（含工業）建任務，由任務經理分析 ──
      if (workQuery.trim() !== query.trim()) {
        routingPreview = await resolveRoutingPreviewForSend({
          query: workQuery,
          mode: options.executionStrategy,
          companyTemplate: options.companyTemplate,
          snapshot: null,
        });
        if (routingPreview) patchAssistantRouting(routingPreview);
      }
      const openTaskWorkspace = usesTaskWorkspace(options.executionStrategy, routingPreview);
      if (!openTaskWorkspace) {
        setSending(false);

        // 構建對話歷史（最近 6 輪，排除當前佔位訊息）
        const currentMessages = activeSession.messages.filter(
          (m) => m.id !== assistantId && m.content.trim(),
        );
        const history = currentMessages.slice(-12).map((m) => ({
          role: m.role,
          content: m.content,
        }));

        sendChatStream(workQuery, sessionId, {
          onPathResolved: (preview) => {
            patchAssistantRouting(preview);
          },
          onPhase: (phase) => {
            updateSession(sessionId, (s) => ({
              ...s,
              updatedAt: Date.now(),
              messages: s.messages.map((m) =>
                m.id === assistantId ? { ...m, streamPhase: phase } : m,
              ),
            }));
          },
          onToken: (token) => {
            updateSession(sessionId, (s) => ({
              ...s,
              updatedAt: Date.now(),
              messages: s.messages.map((m) => {
                if (m.id !== assistantId) return m;
                const raw = `${m.streamRaw ?? m.content}${token}`;
                const { thinking, content } = splitThink(raw);
                return { ...m, streamRaw: raw, content, thinking };
              }),
            }));
          },
          onAnswer: (answer) => {
            updateSession(sessionId, (s) => ({
              ...s,
              updatedAt: Date.now(),
              messages: s.messages.map((m) => {
                if (m.id !== assistantId) return m;
                const { thinking, content } = splitThink(answer);
                return {
                  ...m,
                  content: content || answer,
                  thinking: thinking || m.thinking,
                  streamRaw: undefined,
                };
              }),
            }));
          },
          onEvaluation: (score, iteration, multiDim) => {
            updateSession(sessionId, (s) => ({
              ...s,
              messages: s.messages.map((m) =>
                m.id === assistantId
                  ? { ...m, meta: { ...m.meta, score, iteration, multiDim } }
                  : m,
              ),
            }));
          },
          onDone: (answer, score, iteration, thinking, billing) => {
            const footnote = billing ? formatChatBillingFootnote(billing) : undefined;
            requestBillingRefresh();
            updateSession(sessionId, (s) => ({
              ...s,
              updatedAt: Date.now(),
              messages: s.messages.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: splitThink(answer || m.content).content || answer || m.content,
                      thinking: thinking || splitThink(answer || '').thinking || m.thinking,
                      streamRaw: undefined,
                      streaming: false,
                      meta: {
                        ...m.meta,
                        score,
                        iteration,
                        billingFootnote: footnote || undefined,
                        billing: billing || undefined,
                      },
                    }
                  : m,
              ),
            }));
          },
          onBilling: (billing: ChatBillingFootnote) => {
            const footnote = formatChatBillingFootnote(billing);
            requestBillingRefresh();
            if (!footnote) return;
            updateSession(sessionId, (s) => ({
              ...s,
              messages: s.messages.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      meta: {
                        ...m.meta,
                        billingFootnote: footnote || m.meta?.billingFootnote,
                        billing: { ...m.meta?.billing, ...billing },
                      },
                    }
                  : m,
              ),
            }));
          },
          onError: (errMsg) => {
            setError(errMsg);
            updateSession(sessionId, (s) => ({
              ...s,
              messages: s.messages.map((m) =>
                m.id === assistantId ? { ...m, streaming: false } : m,
              ),
            }));
          },
        }, history, {
          semantic_lock: semanticLock,
          ui_language: i18n.language,
          executionStrategy: options.executionStrategy,
        });
        return;
      }

      // ── 統一模式：公司運行時路徑走任務 API + WebSocket ──
      try {
        const { task_id } = await createTask(
          workQuery,
          options.executionStrategy,
          options.companyTemplate,
          {
            ...options.taskOptions,
            semantic_brief: workQuery !== query ? workQuery : options.taskOptions?.semantic_brief,
            auditor_ticket:
              (semanticLock.ticket as TaskOptions['auditor_ticket'])
              ?? options.taskOptions?.auditor_ticket,
            precomputed_planner: precomputedPlanner,
            ui_language: i18n.language,
          },
        );
        updateSession(sessionId, (s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === assistantId ? { ...m, taskId: task_id } : m,
          ),
        }));

        setSending(false);

        // 任務進度監聽移交 useTaskProgressStream（WebSocket 優先，降級輪詢）
        startTaskProgressStream({
          taskId: task_id,
          sessionId,
          assistantId,
          updateSession,
          patchAssistantRouting,
          setError,
          setRightPanelTask,
        });
      } catch (err) {
        setError((err as Error).message);
        updateSession(sessionId, (s) => ({
          ...s,
          messages: s.messages.filter((m) => m.id !== assistantId),
        }));
        setSending(false);
      }
    },
    [activeSession, i18n.language, updateSession],
  );

  const handleRetry = useCallback(() => {
    if (lastQuery)
      void sendQuery(lastQuery, {
        executionStrategy: 'auto',
        companyTemplate: 'quick_task',
      });
  }, [lastQuery, sendQuery]);

  // ── 快捷建议 ──
  const handleSuggest = useCallback(
    (text: string, company: boolean) => {
      void sendQuery(text, {
        executionStrategy: company ? 'company' : 'auto',
        companyTemplate: 'quick_task',
      });
    },
    [sendQuery],
  );

  return { sending, lastQuery, sendQuery, handleRetry, handleSuggest };
}
