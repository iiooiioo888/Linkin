/**
 * 任務進度監聽：優先 WebSocket 推送，失效時降級 REST 輪詢（自 sendQuery 抽出，行為不變）。
 *
 * 原本在 sendQuery 內同步建立連線／輪詢；抽出後仍由呼叫端（useChatSend）在任務建立後
 * 立即呼叫 startTaskProgressStream，不新增 effect 或卸載清理，維持與原邏輯等價。
 */
import { useCallback } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { fetchTask, TaskWebSocket } from '../api/client';
import type { TaskWsMessage } from '../api/client';
import { coerceTaskProgressStatus, isTerminalTaskStatus } from '../lib/chatWorkspace';
import { parseRoutingPreview } from '../lib/routingPreview';
import type { ChatSession, RoutingPreview, TaskProgress } from '../types';
import { usesIndustrialStages } from '../types';

export interface TaskProgressStreamParams {
  /** 已建立的公司任務 id */
  taskId: string;
  sessionId: string;
  /** 這輪要更新的 assistant 佔位訊息 id */
  assistantId: string;
  updateSession: (id: string, updater: (s: ChatSession) => ChatSession) => void;
  /** 把 path_resolved 預覽補寫進該則訊息 */
  patchAssistantRouting: (preview: RoutingPreview) => void;
  setError: Dispatch<SetStateAction<string | null>>;
  setRightPanelTask: Dispatch<SetStateAction<TaskProgress | null>>;
}

export interface UseTaskProgressStreamResult {
  startTaskProgressStream: (params: TaskProgressStreamParams) => void;
}

export function useTaskProgressStream(): UseTaskProgressStreamResult {
  const startTaskProgressStream = useCallback((params: TaskProgressStreamParams) => {
    const {
      taskId,
      sessionId,
      assistantId,
      updateSession,
      patchAssistantRouting,
      setError,
      setRightPanelTask,
    } = params;

    // ── 任务进度监听：优先 WebSocket，降级轮询 ──
    let finished = false;
    let wsClient: TaskWebSocket | null = null;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let lastProgress: TaskProgress | null = null;

    const applyProgress = (progress: TaskProgress) => {
      // 執行中若新快照缺 raho／pending 欄位，保留上一幀待決，避免決策列被輪詢冲掉
      const progressRunning =
        progress.status === 'running' || progress.status === 'pending';
      let mergedProgress = progress;
      if (progressRunning && lastProgress?.raho) {
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
      const terminal = isTerminalTaskStatus(mergedProgress.status);
      const running =
        !terminal &&
        (mergedProgress.status === 'running' || mergedProgress.status === 'pending');
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
                streaming: terminal ? false : running,
              }
            : m,
        ),
      }));

      // OPC 任务自动打开右侧面板
      if (usesIndustrialStages(progress) && progress.opc_state) {
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
        if (usesIndustrialStages(progress)) {
          setRightPanelTask(progress);
        }
        wsClient?.close();
        if (pollTimer) clearTimeout(pollTimer);
      }
      if (
        (progress.status === 'failed' ||
          progress.status === 'cancelled' ||
          progress.status === 'interrupted') &&
        !finished
      ) {
        finished = true;
        updateSession(sessionId, (s) => ({
          ...s,
          messages: s.messages.map((m) =>
            m.id === assistantId ? { ...m, streaming: false } : m,
          ),
        }));
        if (progress.status === 'failed') {
          setError(progress.error || '任务执行失败');
        }
        wsClient?.close();
        if (pollTimer) clearTimeout(pollTimer);
      }
    };

    // 轮询降级方案：WS onClose 与 3 秒检查都会调用，这里保证只跑一条链
    let polling = false;
    const pollProgress = async () => {
      if (finished || polling) return;
      polling = true;
      try {
        const progress = await fetchTask(taskId);
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
      } else if (msg.event === 'path_resolved') {
        const preview = parseRoutingPreview(msg.data);
        if (preview) {
          patchAssistantRouting(preview);
          if (lastProgress) {
            applyProgress({
              ...lastProgress,
              resolved_path: preview.path,
            });
          } else {
            fetchTask(taskId).then(applyProgress).catch(() => {});
          }
        }
      } else if (msg.event === 'task_finished') {
        // 任务结束：获取最终状态
        fetchTask(taskId).then(applyProgress).catch(() => {
          // 降级：使用事件数据
          const data = msg.data;
          if (lastProgress) {
            const validStatus = coerceTaskProgressStatus(data.status);
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
        fetchTask(taskId).then(applyProgress).catch(() => {});
      } else if (
        msg.event === 'phase_change' ||
        msg.event === 'evaluation' ||
        msg.event === 'grill_raised' ||
        msg.event === 'campaign_planned' ||
        msg.event === 'inspector_verdict'
      ) {
        // 增量更新：获取最新状态
        fetchTask(taskId).then(applyProgress).catch(() => {});
      }
    };

    // 尝试 WebSocket 连接
    try {
      wsClient = new TaskWebSocket(
        taskId,
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

  }, []);

  return { startTaskProgressStream };
}
