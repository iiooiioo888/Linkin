/**
 * EvoLoop 主应用 — IDE 风格单页布局。
 *
 * 使用 AppShell 作为根布局，整合会话管理、聊天视图、
 * 控制面版视图、OPC 右侧诊断面板。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ChatMessage, ChatSession, TaskProgress } from './types';
import { cancelTask, createTask, fetchConfig, fetchMemories, fetchTask, planBattle, resumeTask, sendChatStream, startUserGrill, streamAuditor, TaskWebSocket } from './api/client';
import type { TaskWsMessage } from './api/client';
import {
  appRouteFromState,
  applyAppRoute,
  getDefaultRoute,
  parseAppRoute,
  routesEqual,
  syncAppRouteHash,
} from './lib/appRoute';
import { isLinkinStudioAgent, requestRoleGrillDesk } from './lib/agentUi';
import {
  loadActiveSessionId,
  loadSessions,
  newSessionId,
  saveActiveSessionId,
  saveSessions,
} from './lib/storage';
import { looksLikeCompanyQuery } from './lib/chatWorkspace';
import { hydrateWorldModules } from './lib/worldModules';
import { splitThink } from './lib/splitThink';
import AppShell from './components/AppShell';
import ContextModal from './components/ContextModal';
import { OPEN_CONTEXT_MODAL_EVENT, type OpenContextModalDetail } from './lib/contextUi';
import type { MonitorTab, ViewKey } from './components/AppShell';
import type { LabSubTab } from './lib/labTabs';
import ChatView from './components/ChatView';
import type { SendOptions } from './components/InputBar';
import MonitorView from './components/MonitorView';
import SettingsModal from './components/SettingsModal';
import TraceView from './components/TraceView';
import TaskDetailView from './components/taskdetail/TaskDetailView';
import RahoOpsView from './components/rahoops/RahoOpsView';

function createSession(): ChatSession {
  const now = Date.now();
  return {
    id: newSessionId(),
    title: '',
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

export default function App() {
  // ── 会话管理 ──
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const loaded = loadSessions();
    return loaded.length > 0 ? loaded : [createSession()];
  });
  const [activeId, setActiveId] = useState<string>(() => {
    const saved = loadActiveSessionId();
    const loaded = loadSessions();
    if (saved && loaded.some((s) => s.id === saved)) return saved;
    return loaded[0]?.id ?? '';
  });

  // ── 发送状态 ──
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState<string | null>(null);

  // ── IDE 布局状态（由 Hash 路由初始化） ──
  const initialRoute = applyAppRoute(parseAppRoute(window.location.hash));
  const [routeReady, setRouteReady] = useState(false);
  const [activeView, setActiveView] = useState<ViewKey>(initialRoute.activeView);
  const [monitorTab, setMonitorTab] = useState<MonitorTab>(initialRoute.monitorTab);
  /** 進入監控「角色 Agent」時預選一位，主區開工作台；名冊在左側外圍 */
  const [focusAgentId, setFocusAgentId] = useState<string | null>(initialRoute.focusAgentId);
  const [focusTaskId, setFocusTaskId] = useState<string | null>(initialRoute.focusTaskId);
  const [traceTaskId, setTraceTaskId] = useState<string | null>(initialRoute.traceTaskId);
  /** 公司運行時席位 I/O 監察整頁的聚焦對象（raho run_id 或 task_id） */
  const [rahoFocus, setRahoFocus] = useState<string | null>(initialRoute.rahoFocus);
  const [labSubTab, setLabSubTab] = useState<LabSubTab>(initialRoute.labSubTab);
  const [rightPanelTask, setRightPanelTask] = useState<TaskProgress | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [contextModal, setContextModal] = useState<{ open: boolean; taskId: string | null }>({
    open: false,
    taskId: null,
  });
  const [memoryCount, setMemoryCount] = useState(0);
  const [decisionPending, setDecisionPending] = useState(false);

  // ── LLM 配置 ──
  const [llmConfigured, setLlmConfigured] = useState<boolean | null>(null);

  const refreshConfigStatus = useCallback(() => {
    fetchConfig()
      .then((cfg) => setLlmConfigured(cfg.configured))
      .catch(() => setLlmConfigured(null));
  }, []);

  useEffect(() => {
    refreshConfigStatus();
  }, [refreshConfigStatus]);

  useEffect(() => {
    void hydrateWorldModules();
  }, []);

  // Hash 路由：初始化正規化 + 狀態同步 + 瀏覽器前進/後退
  useEffect(() => {
    const boot = parseAppRoute(window.location.hash);
    syncAppRouteHash(boot);
    setRouteReady(true);
  }, []);

  useEffect(() => {
    if (!routeReady) return;
    syncAppRouteHash(
      appRouteFromState({
        activeView,
        monitorTab,
        focusAgentId,
        focusTaskId,
        traceTaskId,
        rahoFocus,
        labSubTab,
      }),
    );
  }, [routeReady, activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId, rahoFocus, labSubTab]);

  useEffect(() => {
    const onHashChange = () => {
      const parsed = parseAppRoute(window.location.hash);
      const current = appRouteFromState({
        activeView,
        monitorTab,
        focusAgentId,
        focusTaskId,
        traceTaskId,
        rahoFocus,
        labSubTab,
      });
      if (routesEqual(current, parsed)) return;
      const next = applyAppRoute(parsed);
      setActiveView(next.activeView);
      setMonitorTab(next.monitorTab);
      setFocusAgentId(next.focusAgentId);
      setFocusTaskId(next.focusTaskId);
      setTraceTaskId(next.traceTaskId);
      setRahoFocus(next.rahoFocus);
      setLabSubTab(next.labSubTab);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId, rahoFocus, labSubTab]);

  useEffect(() => {
    const onPeek = (ev: Event) => {
      const detail = (ev as CustomEvent<OpenContextModalDetail>).detail;
      // 僅使用呼叫方顯式傳入的 taskId；禁止用 monitor focusTaskId 頂替（避免跨對話洩漏）
      const explicit =
        detail && Object.prototype.hasOwnProperty.call(detail, 'taskId')
          ? detail.taskId ?? null
          : null;
      setContextModal({ open: true, taskId: explicit });
    };
    window.addEventListener(OPEN_CONTEXT_MODAL_EVENT, onPeek);
    return () => window.removeEventListener(OPEN_CONTEXT_MODAL_EVENT, onPeek);
  }, []);

  const navigateRoute = useCallback(
    (patch: Partial<ReturnType<typeof getDefaultRoute>>) => {
      const route = appRouteFromState({
        activeView: patch.view ?? activeView,
        monitorTab: patch.monitorTab ?? monitorTab,
        focusAgentId: patch.focusAgentId !== undefined ? patch.focusAgentId : focusAgentId,
        focusTaskId: patch.focusTaskId !== undefined ? patch.focusTaskId : focusTaskId,
        traceTaskId: patch.traceTaskId !== undefined ? patch.traceTaskId : traceTaskId,
        rahoFocus: patch.rahoFocus !== undefined ? patch.rahoFocus : rahoFocus,
        labSubTab: patch.labSubTab ?? labSubTab,
      });
      const applied = applyAppRoute(route);
      setActiveView(applied.activeView);
      setMonitorTab(applied.monitorTab);
      setFocusAgentId(applied.focusAgentId);
      setFocusTaskId(applied.focusTaskId);
      setTraceTaskId(applied.traceTaskId);
      setRahoFocus(applied.rahoFocus);
      setLabSubTab(applied.labSubTab);
    },
    [activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId, rahoFocus, labSubTab],
  );

  useEffect(() => {
    fetchMemories(1, 0)
      .then((data) => setMemoryCount(data.total ?? 0))
      .catch(() => setMemoryCount(0));
    const timer = setInterval(() => {
      fetchMemories(1, 0)
        .then((data) => setMemoryCount(data.total ?? 0))
        .catch(() => {});
    }, 30000);
    return () => clearInterval(timer);
  }, []);

  // 初次加载时若无有效 activeId，使用第一个会话
  useEffect(() => {
    if (!activeId && sessions.length > 0) {
      setActiveId(sessions[0].id);
    }
  }, [activeId, sessions]);

  // 持久化
  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);
  useEffect(() => {
    if (activeId) saveActiveSessionId(activeId);
  }, [activeId]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? sessions[0],
    [sessions, activeId],
  );

  const updateSession = useCallback(
    (id: string, updater: (s: ChatSession) => ChatSession) => {
      setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
    },
    [],
  );

  const handleNewSession = useCallback(() => {
    const session = createSession();
    setSessions((prev) => [session, ...prev]);
    setActiveId(session.id);
    setError(null);
    setRightPanelTask(null);
  }, []);

  const handleSelectSession = useCallback((id: string) => {
    setActiveId(id);
    setError(null);
    setRightPanelTask(null);
  }, []);

  const handleDeleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const remaining = prev.filter((s) => s.id !== id);
        if (id === activeId) {
          const next = remaining.length > 0 ? remaining[0] : createSession();
          if (remaining.length === 0) remaining.push(next);
          setActiveId(next.id);
        }
        return remaining;
      });
    },
    [activeId],
  );

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
      if (!options.skipGrill && options.executionStrategy !== 'simple') {
        try {
          const grill =
            options.executionStrategy === 'company'
              ? await streamAuditor({ query })
              : await startUserGrill(query, options.executionStrategy);
          if (grill.should_grill && !grill.locked && !grill.terminated) {
            updateSession(sessionId, (s) => ({
              ...s,
              updatedAt: Date.now(),
              messages: s.messages.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      streaming: false,
                      content: grill.question?.question || '請先接受需求審計',
                      grill: {
                        ...grill,
                        originalQuery: query,
                        history: grill.question
                          ? [{ role: 'assistant', content: grill.question.question, why: grill.question.why }]
                          : [],
                        sendOptions: {
                          executionStrategy: options.executionStrategy,
                          companyTemplate: options.companyTemplate,
                          taskOptions: options.taskOptions,
                        },
                      },
                    }
                  : m,
              ),
            }));
            setSending(false);
            return;
          }
          if (grill.terminated) {
            updateSession(sessionId, (s) => ({
              ...s,
              updatedAt: Date.now(),
              messages: s.messages.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      streaming: false,
                      content: grill.termination_report || '需求審計失敗',
                      grill: { ...grill, originalQuery: query, history: [] },
                    }
                  : m,
              ),
            }));
            setSending(false);
            return;
          }
          // 僅當真的有 L4 門票（經過完整審計並 APPROVED_FOR_PLANNING）才要 L3 拆解；
          // grill 直通（寒暄／簡單 query，無門票）時直接執行，
          // 否則 planBattle 會以「缺少 APPROVED_FOR_PLANNING」硬擋下所有任務。
          if (grill.locked && grill.locked_brief && grill.ticket) {
            workQuery = grill.locked_brief;
            semanticLock = {
              locked: true,
              locked_brief: grill.locked_brief,
              ticket: grill.ticket ?? null,
            };
            try {
              const battle = await planBattle(
                (grill.ticket ?? undefined) as Record<string, unknown> | undefined,
                grill.locked_brief,
              );
              updateSession(sessionId, (s) => ({
                ...s,
                updatedAt: Date.now(),
                messages: s.messages.map((m) =>
                  m.id === assistantId ? { ...m, battle, grill: { ...grill, originalQuery: query } } : m,
                ),
              }));
              if (battle.status === 'REJECT_TO_L4' || battle.status === 'ESCALATE_TO_USER') {
                updateSession(sessionId, (s) => ({
                  ...s,
                  messages: s.messages.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          streaming: false,
                          content:
                            battle.status === 'REJECT_TO_L4'
                              ? 'L3 退回 L4：門票缺件，拒絕拆解。'
                              : 'L3 上交用戶：約束內不可行。',
                          battle,
                        }
                      : m,
                  ),
                }));
                setSending(false);
                return;
              }
            } catch {
              // L3 不可用時仍帶門票進入公司運行時
            }
          }
        } catch {
          // Grill 不可用時降級直通執行
        }
      }
      if (options.taskOptions?.semantic_brief || options.taskOptions?.auditor_ticket) {
        semanticLock = {
          locked: true,
          locked_brief: options.taskOptions.semantic_brief || workQuery,
          ticket: options.taskOptions.auditor_ticket ?? null,
        };
      }

      // ── 統一模式：寒暄／簡單走 SSE；公司或長文交付建任務，主頁才分裂監控欄 ──
      const openTaskWorkspace =
        options.executionStrategy === 'company' ||
        (options.executionStrategy === 'auto' && looksLikeCompanyQuery(workQuery));
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
          onDone: (answer, score, iteration, thinking) => {
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
                      meta: { score, iteration },
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
        }, history, { semantic_lock: semanticLock });
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
            auditor_ticket: options.taskOptions?.auditor_ticket,
          },
        );
        updateSession(sessionId, (s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === assistantId ? { ...m, taskId: task_id } : m,
          ),
        }));

        setSending(false);

        // ── 任务进度监听：优先 WebSocket，降级轮询 ──
        let finished = false;
        let wsClient: TaskWebSocket | null = null;
        let pollTimer: ReturnType<typeof setTimeout> | null = null;
        let lastProgress: TaskProgress | null = null;

        const applyProgress = (progress: TaskProgress) => {
          // 執行中若新快照缺 raho／pending 欄位，保留上一幀待決，避免決策列被輪詢冲掉
          const running =
            progress.status === 'running' || progress.status === 'pending';
          let mergedProgress = progress;
          if (running && lastProgress?.raho) {
            const prevPending = lastProgress.raho.pending_decisions ?? [];
            if (!progress.raho) {
              mergedProgress = { ...progress, raho: { ...lastProgress.raho } };
            } else if (!Array.isArray(progress.raho.pending_decisions) && prevPending.length > 0) {
              mergedProgress = {
                ...progress,
                raho: { ...progress.raho, pending_decisions: prevPending },
              };
            }
          }
          lastProgress = mergedProgress;
          const liveDraft = mergedProgress.answer?.trim() ?? '';
          const roleThink = Object.values(mergedProgress.kanban ?? {})
            .flat()
            .map((it) => String(it.thinking ?? '').trim())
            .filter(Boolean)
            .join('\n\n');
          const eventThink = (mergedProgress.events ?? [])
            .map((e) => String(e.data.thinking ?? '').trim())
            .filter(Boolean)
            .join('\n\n');
          updateSession(sessionId, (s) => ({
            ...s,
            updatedAt: Date.now(),
            messages: s.messages.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    taskState: mergedProgress,
                    content: liveDraft || m.content,
                    thinking: roleThink || eventThink || m.thinking,
                    streaming: running,
                  }
                : m,
            ),
          }));

          // OPC 任务自动打开右侧面板
          if (progress.resolved_path === 'opc' && progress.opc_state) {
            setRightPanelTask(progress);
          }

          if (progress.status === 'completed' && !finished) {
            finished = true;
            updateSession(sessionId, (s) => ({
              ...s,
              messages: s.messages.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: progress.answer || '（未取得回答）',
                      streaming: false,
                      meta: { score: progress.score, iteration: progress.iteration },
                    }
                  : m,
              ),
            }));
            if (progress.resolved_path === 'opc') {
              setRightPanelTask(progress);
            }
            wsClient?.close();
            if (pollTimer) clearTimeout(pollTimer);
          }
          if (progress.status === 'failed' && !finished) {
            finished = true;
            updateSession(sessionId, (s) => ({
              ...s,
              messages: s.messages.map((m) =>
                m.id === assistantId ? { ...m, streaming: false } : m,
              ),
            }));
            setError(progress.error || '任务执行失败');
            wsClient?.close();
            if (pollTimer) clearTimeout(pollTimer);
          }
        };

        // 轮询降级方案
        const pollProgress = async () => {
          if (finished) return;
          try {
            const progress = await fetchTask(task_id);
            applyProgress(progress);
          } catch {
            // 忽略单次轮询失败
          }
          if (!finished) {
            pollTimer = setTimeout(pollProgress, 1500);
          }
        };

        // WebSocket 消息处理
        const handleWsMessage = (msg: TaskWsMessage) => {
          if (msg.event === 'snapshot') {
            // 初始快照
            applyProgress(msg.data as unknown as TaskProgress);
          } else if (msg.event === 'task_finished') {
            // 任务结束：获取最终状态
            fetchTask(task_id).then(applyProgress).catch(() => {
              // 降级：使用事件数据
              const data = msg.data;
              if (lastProgress) {
                const statusValue = data.status;
                const validStatus: TaskProgress['status'] =
                  statusValue === 'completed' || statusValue === 'failed' ||
                  statusValue === 'running' || statusValue === 'pending'
                    ? statusValue
                    : 'completed';
                applyProgress({
                  ...lastProgress,
                  status: validStatus,
                  score: (data.score as number) ?? null,
                  iteration: (data.iteration as number) ?? 0,
                  error: (data.error as string) ?? '',
                });
              }
            });
          } else if (msg.event === 'user_decision_needed') {
            const data = msg.data as Record<string, unknown>;
            if (lastProgress && data.decision_id) {
              const incoming = {
                decision_id: String(data.decision_id),
                run_id: String(data.run_id || lastProgress.raho?.run_id || ''),
                item_id: String(data.item_id || ''),
                layer: 5,
                layer_label: 'L5 用戶',
                role_id: 'user',
                role_label: 'L5 用戶',
                question: String(data.question || ''),
                choices: Array.isArray(data.choices) ? (data.choices as Array<{ key: string; label: string }>) : [],
                ttl: typeof data.ttl === 'number' ? data.ttl : undefined,
                created_at: typeof data.created_at === 'number' ? data.created_at : Date.now() / 1000,
                remaining_sec: typeof data.remaining_sec === 'number' ? data.remaining_sec : undefined,
                blocked: true,
              };
              const prev = lastProgress.raho?.pending_decisions ?? [];
              const merged = [
                ...prev.filter((p) => p.decision_id !== incoming.decision_id),
                incoming,
              ];
              applyProgress({
                ...lastProgress,
                raho: {
                  ...(lastProgress.raho ?? {}),
                  run_id: incoming.run_id || lastProgress.raho?.run_id,
                  pending_decisions: merged,
                },
              });
            }
            fetchTask(task_id).then(applyProgress).catch(() => {});
          } else if (
            msg.event === 'phase_change' ||
            msg.event === 'evaluation' ||
            msg.event === 'grill_raised' ||
            msg.event === 'campaign_planned' ||
            msg.event === 'inspector_verdict'
          ) {
            // 增量更新：获取最新状态
            fetchTask(task_id).then(applyProgress).catch(() => {});
          }
        };

        // 尝试 WebSocket 连接
        try {
          wsClient = new TaskWebSocket(
            task_id,
            handleWsMessage,
            () => {
              // WebSocket 关闭且任务未完成 → 降级轮询
              if (!finished) {
                pollProgress();
              }
            },
          );
          wsClient.connect();

          // 3 秒后检查连接状态，未连接则启动轮询
          setTimeout(() => {
            if (!wsClient?.connected && !finished) {
              pollProgress();
            }
          }, 3000);
        } catch {
          // WebSocket 不可用，直接轮询
          pollProgress();
        }
      } catch (err) {
        setError((err as Error).message);
        updateSession(sessionId, (s) => ({
          ...s,
          messages: s.messages.filter((m) => m.id !== assistantId),
        }));
        setSending(false);
      }
    },
    [activeSession, updateSession],
  );

  const handleGrillAnswer = useCallback(
    async (messageId: string, answer: string, forceLock = false) => {
      if (!activeSession) return;
      const sessionId = activeSession.id;
      const msg = activeSession.messages.find((m) => m.id === messageId);
      const grill = msg?.grill;
      if (!msg || !grill?.session_id) return;
      setSending(true);
      setError(null);
      try {
        const next = await streamAuditor({
          sessionId: grill.session_id,
          answer,
          forceLock,
        });
        const history = [
          ...(grill.history ?? []),
          { role: 'user' as const, content: answer },
          ...(next.question
            ? [{ role: 'assistant' as const, content: next.question.question, why: next.question.why }]
            : []),
        ];
        updateSession(sessionId, (s) => ({
          ...s,
          updatedAt: Date.now(),
          messages: s.messages.map((m) =>
            m.id === messageId
              ? {
                  ...m,
                  content:
                    next.termination_report
                    || next.question?.question
                    || (next.locked ? '需求已鎖定，開始規劃。' : m.content),
                  grill: { ...grill, ...next, history, originalQuery: grill.originalQuery, sendOptions: grill.sendOptions },
                }
              : m,
          ),
        }));
        if (next.terminated) {
          return;
        }
        if (next.locked) {
          const opts = grill.sendOptions ?? {
            executionStrategy: (msg.executionStrategy ?? 'auto') as SendOptions['executionStrategy'],
            companyTemplate: 'quick_task' as const,
          };
          let battleBlocked = false;
          try {
            const battle = await planBattle(
              (next.ticket ?? undefined) as Record<string, unknown> | undefined,
              next.locked_brief || '',
            );
            updateSession(sessionId, (s) => ({
              ...s,
              messages: s.messages.map((m) =>
                m.id === messageId ? { ...m, battle } : m,
              ),
            }));
            if (battle.status === 'REJECT_TO_L4' || battle.status === 'ESCALATE_TO_USER') {
              battleBlocked = true;
            }
          } catch {
            // L3 不可用時仍進入公司運行時
          }
          if (battleBlocked) {
            return;
          }
          void sendQuery(next.locked_brief || grill.originalQuery || answer, {
            executionStrategy: opts.executionStrategy,
            companyTemplate: (opts.companyTemplate as SendOptions['companyTemplate']) || 'quick_task',
            skipGrill: true,
            taskOptions: {
              ...opts.taskOptions,
              semantic_brief: next.locked_brief || grill.originalQuery,
              auditor_ticket: next.ticket ?? undefined,
            },
          });
        }
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setSending(false);
      }
    },
    [activeSession, sendQuery, updateSession],
  );

  const handleBattlePick = useCallback(
    (messageId: string, choice: string) => {
      const msg = activeSession?.messages.find((m) => m.id === messageId);
      const grill = msg?.grill;
      const opts = grill?.sendOptions ?? {
        executionStrategy: (msg?.executionStrategy ?? 'auto') as SendOptions['executionStrategy'],
        companyTemplate: 'quick_task' as const,
      };
      const baseTicket = grill?.ticket ?? opts.taskOptions?.auditor_ticket ?? {};
      const ticket = { ...baseTicket, user_override: choice };
      updateSession(activeSession?.id ?? '', (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.id === messageId
            ? {
                ...m,
                battle: m.battle
                  ? { ...m.battle, waiting_for_user_decision: false, status: 'PLAN_READY' }
                  : m.battle,
              }
            : m,
        ),
      }));
      void sendQuery(grill?.locked_brief || grill?.originalQuery || choice, {
        executionStrategy: opts.executionStrategy,
        companyTemplate: (opts.companyTemplate as SendOptions['companyTemplate']) || 'quick_task',
        skipGrill: true,
        taskOptions: {
          ...opts.taskOptions,
          semantic_brief: grill?.locked_brief || grill?.originalQuery,
          auditor_ticket: ticket,
        },
      });
    },
    [activeSession, sendQuery, updateSession],
  );

  const handleRetry = useCallback(() => {
    if (lastQuery)
      void sendQuery(lastQuery, {
        executionStrategy: 'auto',
        companyTemplate: 'quick_task',
      });
  }, [lastQuery, sendQuery]);

  // ── 任務詳情整頁（#/task/{taskId}）──
  const [taskDetail, setTaskDetail] = useState<TaskProgress | null>(null);
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [taskDetailError, setTaskDetailError] = useState<string | null>(null);

  const loadTaskDetail = useCallback(async (taskId: string) => {
    setTaskDetailLoading(true);
    try {
      // events_limit=0：詳情頁要完整事件流，不受列表頁 50 條截斷限制
      const fresh = await fetchTask(taskId, 0);
      setTaskDetail(fresh);
      setTaskDetailError(null);
    } catch (err) {
      setTaskDetailError((err as Error).message || '讀取任務詳情失敗');
    } finally {
      setTaskDetailLoading(false);
    }
  }, []);

  const openTaskDetail = useCallback(
    (task: TaskProgress) => {
      if (!task?.task_id) return;
      setTaskDetail(task);
      setTaskDetailError(null);
      navigateRoute({ view: 'task', focusTaskId: task.task_id });
    },
    [navigateRoute],
  );

  // OPC 任務保留右側六級診斷面板；公司／簡單任務進詳情整頁
  const openTaskOrPanel = useCallback(
    (task: TaskProgress) => {
      if (task.resolved_path === 'opc') {
        setRightPanelTask(task);
        return;
      }
      openTaskDetail(task);
    },
    [openTaskDetail],
  );

  const handleOpenRaho = useCallback(
    (focus: string) => {
      navigateRoute({ view: 'raho', rahoFocus: focus || null });
    },
    [navigateRoute],
  );

  useEffect(() => {
    if (activeView !== 'task' || !focusTaskId) return;
    void loadTaskDetail(focusTaskId);
  }, [activeView, focusTaskId, loadTaskDetail]);

  const handleTaskCancel = useCallback(() => {
    if (!focusTaskId) return;
    void cancelTask(focusTaskId)
      .then(() => loadTaskDetail(focusTaskId))
      .catch((err: Error) => setTaskDetailError(err.message || '請求取消失敗'));
  }, [focusTaskId, loadTaskDetail]);

  const handleTaskResume = useCallback(() => {
    if (!focusTaskId) return;
    void resumeTask(focusTaskId)
      .then(() => loadTaskDetail(focusTaskId))
      .catch((err: Error) => setTaskDetailError(err.message || '斷點續跑失敗'));
  }, [focusTaskId, loadTaskDetail]);

  // ── 从消息打开任务详情 ──
  const handleOpenTask = useCallback(
    (messageId: string) => {
      const msg = activeSession?.messages.find((m) => m.id === messageId);
      if (!msg?.taskState) return;
      openTaskOrPanel(msg.taskState);
    },
    [activeSession, openTaskOrPanel],
  );

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

  // ── Dashboard 任务打开 ──
  const handleDashboardOpenTask = useCallback((task: TaskProgress) => {
    openTaskOrPanel(task);
  }, [openTaskOrPanel]);

  // ── 打開執行軌跡視圖 ──
  const handleOpenTrace = useCallback(
    (taskId: string) => {
      navigateRoute({ view: 'traces', traceTaskId: taskId });
    },
    [navigateRoute],
  );

  const handleViewChange = useCallback(
    (view: ViewKey) => {
      if (view === 'monitor') {
        // 從其他主視圖切回監控時才清掉 focus；已在監控內則保留書籤路由
        const resetFocus = activeView !== 'monitor';
        navigateRoute({
          view,
          monitorTab,
          focusAgentId: resetFocus ? null : focusAgentId,
          focusTaskId: resetFocus ? null : focusTaskId,
        });
        return;
      }
      if (view === 'traces') {
        navigateRoute({ view, traceTaskId });
        return;
      }
      navigateRoute({ view: 'chat', focusAgentId: null, focusTaskId: null, traceTaskId: null });
    },
    [navigateRoute, activeView, monitorTab, focusAgentId, focusTaskId, traceTaskId],
  );

  const handleMonitorTabChange = useCallback(
    (tab: MonitorTab) => {
      if (tab === 'grill') {
        requestRoleGrillDesk(focusAgentId && !isLinkinStudioAgent(focusAgentId) ? focusAgentId : undefined);
      }
      const resolved = tab === 'grill' ? 'agents' : tab;
      const keepAgent =
        (resolved === 'agents' && !isLinkinStudioAgent(focusAgentId)) ||
        (resolved === 'studio' && isLinkinStudioAgent(focusAgentId));
      navigateRoute({
        view: 'monitor',
        monitorTab: resolved,
        focusAgentId: keepAgent ? focusAgentId : null,
        focusTaskId: resolved === 'tasks' ? focusTaskId : null,
        labSubTab: resolved === 'lab' ? labSubTab : 'prompt',
      });
    },
    [navigateRoute, focusAgentId, focusTaskId, labSubTab],
  );

  const handleLabSubTabChange = useCallback(
    (sub: LabSubTab) => {
      navigateRoute({ view: 'monitor', monitorTab: 'lab', labSubTab: sub });
    },
    [navigateRoute],
  );

  const handleFocusAgent = useCallback(
    (id: string | null) => {
      if (id) {
        navigateRoute({
          view: 'monitor',
          monitorTab: isLinkinStudioAgent(id) ? 'studio' : 'agents',
          focusAgentId: id,
          focusTaskId: null,
        });
        return;
      }
      navigateRoute({
        view: 'monitor',
        monitorTab,
        focusAgentId: null,
      });
    },
    [navigateRoute, monitorTab],
  );

  const handleFocusTask = useCallback(
    (id: string | null) => {
      if (id) {
        navigateRoute({
          view: 'monitor',
          monitorTab: 'tasks',
          focusTaskId: id,
          focusAgentId: null,
        });
        return;
      }
      navigateRoute({
        view: 'monitor',
        monitorTab,
        focusTaskId: null,
      });
    },
    [navigateRoute, monitorTab],
  );

  const handleTraceTaskChange = useCallback(
    (id: string | null) => {
      navigateRoute({ view: 'traces', traceTaskId: id });
    },
    [navigateRoute],
  );

  const handleDecisionPending = useCallback((hasPending: boolean) => {
    setDecisionPending(hasPending);
  }, []);

  const handleDecisionResolved = useCallback(
    (decisionId?: string) => {
      setDecisionPending(false);
      if (!activeSession?.id) return;
      const sid = activeSession.id;
      updateSession(sid, (s) => ({
        ...s,
        messages: s.messages.map((m) => {
          const pending = m.taskState?.raho?.pending_decisions;
          if (!pending?.length) return m;
          const next = decisionId
            ? pending.filter((p) => p.decision_id !== decisionId)
            : [];
          return {
            ...m,
            taskState: {
              ...m.taskState!,
              raho: { ...m.taskState!.raho, pending_decisions: next },
            },
          };
        }),
      }));
    },
    [activeSession?.id, updateSession],
  );

  // ── 状态栏信息 ──
  const statusInfo = useMemo(
    () => ({
      taskCount: sessions.reduce((sum, s) => sum + s.messages.filter((m) => m.taskId).length, 0),
      memoryCount,
    }),
    [sessions, memoryCount],
  );

  return (
    <>
      <AppShell
        activeView={activeView}
        onViewChange={handleViewChange}
        rightPanelTask={rightPanelTask}
        onRightPanelClose={() => setRightPanelTask(null)}
        sessions={sessions}
        activeSessionId={activeSession?.id ?? ''}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onDeleteSession={handleDeleteSession}
        llmConfigured={llmConfigured}
        onOpenSettings={() => setSettingsOpen(true)}
        monitorTab={monitorTab}
        onMonitorTabChange={handleMonitorTabChange}
        focusAgentId={focusAgentId}
        onFocusAgent={handleFocusAgent}
        focusTaskId={focusTaskId}
        onFocusTask={handleFocusTask}
        traceTaskId={traceTaskId}
        onTraceTaskChange={handleTraceTaskChange}
        labSubTab={labSubTab}
        onLabSubTabChange={handleLabSubTabChange}
        statusInfo={statusInfo}
        forceCloseSidebar={decisionPending}
      >
        {activeView === 'chat' && (
          <ChatView
            messages={activeSession?.messages ?? []}
            sessionId={activeSession?.id ?? ''}
            loading={false}
            sending={sending}
            error={error}
            lastQuery={lastQuery}
            llmConfigured={llmConfigured}
            onOpenSettings={() => setSettingsOpen(true)}
            onSend={sendQuery}
            onRetry={handleRetry}
            onDismissError={() => setError(null)}
            onOpenTask={handleOpenTask}
            onOpenTrace={handleOpenTrace}
            onSuggest={handleSuggest}
            onGrillAnswer={handleGrillAnswer}
            onBattlePick={handleBattlePick}
            onDecisionPending={handleDecisionPending}
            onDecisionResolved={handleDecisionResolved}
          />
        )}

        {activeView === 'monitor' && (
          <MonitorView
            onOpenTask={handleDashboardOpenTask}
            onOpenTrace={handleOpenTrace}
            activeTab={monitorTab}
            onTabChange={handleMonitorTabChange}
            focusAgentId={focusAgentId}
            onFocusAgent={handleFocusAgent}
            focusTaskId={focusTaskId}
            onFocusTask={handleFocusTask}
            labSubTab={labSubTab}
            onLabSubTabChange={handleLabSubTabChange}
          />
        )}
        {activeView === 'traces' && (
          <TraceView
            taskId={traceTaskId}
            onTaskIdChange={handleTraceTaskChange}
          />
        )}

        {activeView === 'task' && (
          <TaskDetailView
            task={taskDetail}
            loading={taskDetailLoading}
            error={taskDetailError}
            onRefresh={() => {
              if (focusTaskId) void loadTaskDetail(focusTaskId);
            }}
            onBack={() => navigateRoute({ view: 'monitor', monitorTab: 'tasks' })}
            onOpenTrace={handleOpenTrace}
            onOpenRaho={handleOpenRaho}
            onCancel={handleTaskCancel}
            onResume={handleTaskResume}
          />
        )}

        {activeView === 'raho' && (
          <RahoOpsView
            focus={rahoFocus}
            onFocusChange={(focus) => navigateRoute({ view: 'raho', rahoFocus: focus })}
            onOpenTask={(taskId) => navigateRoute({ view: 'task', focusTaskId: taskId })}
            onBack={() => navigateRoute({ view: 'monitor', monitorTab: 'agents' })}
          />
        )}
      </AppShell>

      {/* LLM 设置弹窗 */}
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSaved={refreshConfigStatus}
        onGoConsole={() => {
          setSettingsOpen(false);
          handleMonitorTabChange('llm');
        }}
        onGoAgents={() => {
          setSettingsOpen(false);
          handleMonitorTabChange('agents');
        }}
        onGoUsage={() => {
          setSettingsOpen(false);
          handleMonitorTabChange('billing');
        }}
      />
      <ContextModal
        open={contextModal.open}
        taskId={contextModal.taskId}
        onClose={() => setContextModal((s) => ({ ...s, open: false }))}
      />
    </>
  );
}