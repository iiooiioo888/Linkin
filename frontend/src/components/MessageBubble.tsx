/** 單則訊息：無框助手回覆 + 任務卡。 */
import { useState } from 'react';
import type { ChatMessage } from '../types';
import { cancelTask, resumeTask, sendFeedback } from '../api/client';
import { splitThink } from '../lib/splitThink';
import { ReflectionRadar } from './ReflectionCharts';
import MarkdownBody from './media/MarkdownBody';
import TaskPanel from './TaskPanel';
import GrillUserCard from './GrillUserCard';
import BattlePlanCard from './BattlePlanCard';
import ErrorState from './ui/ErrorState';


interface MessageBubbleProps {
  message: ChatMessage;
  sessionId: string;
  onOpenTask?: () => void;
  onOpenTrace?: (taskId: string) => void;
  /** 開啟對話底部詳細區 Context（綁定該訊息任務） */
  onOpenContext?: (taskId: string) => void;
  onGrillAnswer?: (messageId: string, answer: string, forceLock?: boolean) => void;
  onBattlePick?: (messageId: string, choice: string) => void;
  variant?: 'default' | 'workspace';
}

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export default function MessageBubble({
  message,
  sessionId,
  onOpenTask,
  onOpenTrace,
  onOpenContext,
  onGrillAnswer,
  onBattlePick,
  variant = 'default',
}: MessageBubbleProps) {
  const [feedbackSent, setFeedbackSent] = useState<1 | 2 | undefined>(message.feedback);
  const [copied, setCopied] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [showRadar, setShowRadar] = useState(false);
  const isUser = message.role === 'user';
  const parsed = splitThink(message.content);
  const thinking = (message.thinking || parsed.thinking).trim();
  const visible = parsed.content || message.content;
  const runningTask =
    message.taskState?.status === 'running' || message.taskState?.status === 'pending';

  const handleCancelTask = async (taskId: string) => {
    setCancelError(null);
    try {
      await cancelTask(taskId);
    } catch (err) {
      setCancelError((err as Error).message);
      setTimeout(() => setCancelError(null), 3000);
    }
  };

  const handleResumeTask = async (taskId: string) => {
    setCancelError(null);
    try {
      await resumeTask(taskId);
    } catch (err) {
      setCancelError((err as Error).message);
      setTimeout(() => setCancelError(null), 3000);
    }
  };

  const handleFeedback = async (rating: 1 | 2) => {
    if (feedbackSent || message.streaming) return;
    await sendFeedback(sessionId, rating);
    setFeedbackSent(rating);
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  };

  const hasActions = !isUser && !message.streaming && (message.content || message.taskState);
  const workspace = variant === 'workspace';

  return (
    <div className={`group flex flex-col gap-2 ${workspace ? '' : isUser ? 'items-end' : 'items-start'}`}>
      {message.taskState && !workspace && (
        <div className="w-full max-w-[min(100%,720px)]">
          <TaskPanel
            task={message.taskState}
            hideDecision
            onOpenFull={onOpenTask}
            onCancel={(taskId) => void handleCancelTask(taskId)}
            onResume={(taskId) => void handleResumeTask(taskId)}
            onOpenTrace={onOpenTrace}
            onOpenContext={onOpenContext}
          />
          {cancelError && (
            <div className="mt-2">
              <ErrorState kind="generic" message={cancelError} compact />
            </div>
          )}
        </div>
      )}

      {message.grill && (
        <div className="w-full max-w-[min(100%,720px)]">
          <GrillUserCard
            grill={message.grill}
            disabled={message.streaming}
            onAnswer={(answer, force) => onGrillAnswer?.(message.id, answer, force)}
          />
        </div>
      )}

      {message.battle && (
        <div className="w-full max-w-[min(100%,720px)]">
          <BattlePlanCard
            battle={message.battle}
            onPickAlternative={(choice) => onBattlePick?.(message.id, choice)}
          />
        </div>
      )}

      {(thinking || visible || (message.streaming && !message.taskState)) && !message.grill && (
        workspace ? (
          <div className={`ws-msg ${isUser ? 'is-user' : 'is-agent'}`}>
            <div
              className="ws-ava ws-ava-lg"
              style={{ background: isUser ? '#8b5cf6' : '#3b82f6' }}
            >
              {isUser ? 'Y' : 'S'}
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
              {isUser ? (
                <div className="ws-msg-b whitespace-pre-wrap">{message.content}</div>
              ) : visible ? (
                <div className="ws-msg-b">
                  <div className="markdown-body">
                    <MarkdownBody markdown={visible} />
                  </div>
                </div>
              ) : (
                <div className="ws-msg-b">{message.streaming ? '生成中…' : ''}</div>
              )}
              <div className="ws-msg-time">{formatTime(message.timestamp)}</div>
            </div>
          </div>
        ) : (
        <div className={`max-w-[min(92%,720px)] min-w-0 ${isUser ? '' : 'w-full'}`}>
          {isUser ? (
            <div className="evo-msg-user whitespace-pre-wrap">{message.content}</div>
          ) : (
            <div className="evo-msg-assistant space-y-3">
              {thinking && (
                <details open={Boolean(message.streaming)} className="rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-2">
                  <summary className="cursor-pointer text-[11px] font-medium text-[#8E8E93]">
                    思考過程{message.streaming ? ' · 進行中' : ''}
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap font-sans text-[12px] leading-relaxed text-[#AEAEB2]">
                    {thinking}
                  </pre>
                </details>
              )}
              {visible ? (
                <div className="markdown-body">
                  {runningTask && (
                    <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-[#636366]">
                      {message.streaming || runningTask ? '生成中' : '回覆'}
                    </p>
                  )}
                  <MarkdownBody markdown={visible} />
                </div>
              ) : (
                message.streaming && !thinking && (
                  <div className="flex items-center gap-2 py-1 text-[13px] text-[#636366]">
                    <span className="inline-flex gap-1">
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#636366]" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#636366] [animation-delay:120ms]" />
                      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#636366] [animation-delay:240ms]" />
                    </span>
                  </div>
                )
              )}
            </div>
          )}
        </div>
        )
      )}

      {hasActions && !workspace && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-0.5 text-[11px] text-[#48484A] opacity-70 transition-opacity group-hover:opacity-100">
          <span>{formatTime(message.timestamp)}</span>
          {message.meta?.score != null && (
            <span className="text-[#30D158]">{message.meta.score.toFixed(1)}</span>
          )}
          {!!message.meta?.iteration && <span>{message.meta.iteration} 輪</span>}
          {message.meta?.billingFootnote ? (
            <span className="text-[#64D2FF]" title="本次扣款摘要">{message.meta.billingFootnote}</span>
          ) : null}
          {message.meta?.multiDim && (
            <button type="button" onClick={() => setShowRadar((v) => !v)} className="hover:text-[#F5F5F7]">
              {showRadar ? '收起評分' : '評分'}
            </button>
          )}
          <button type="button" onClick={() => void handleCopy()} className="hover:text-[#F5F5F7]">
            {copied ? '已複製' : '複製'}
          </button>
          <button
            type="button"
            onClick={() => void handleFeedback(2)}
            disabled={!!feedbackSent}
            className={`disabled:opacity-30 ${feedbackSent === 2 ? 'text-[#30D158]' : 'hover:text-[#F5F5F7]'}`}
          >
            讚
          </button>
          <button
            type="button"
            onClick={() => void handleFeedback(1)}
            disabled={!!feedbackSent}
            className={`disabled:opacity-30 ${feedbackSent === 1 ? 'text-[#FF453A]' : 'hover:text-[#F5F5F7]'}`}
          >
            差
          </button>
        </div>
      )}

      {isUser && !workspace && (
        <span className="px-0.5 text-[10px] text-[#48484A] opacity-0 transition-opacity group-hover:opacity-70">
          {formatTime(message.timestamp)}
        </span>
      )}

      {showRadar && message.meta?.multiDim && !message.streaming && (
        <div className="w-full max-w-xs">
          <ReflectionRadar multiDim={message.meta.multiDim} height={130} />
        </div>
      )}
    </div>
  );
}
