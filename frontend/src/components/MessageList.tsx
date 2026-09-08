/**
 * 訊息列表：居中窄欄，空態極簡。
 */
import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../types';
import MessageBubble from './MessageBubble';

interface MessageListProps {
  messages: ChatMessage[];
  sessionId: string;
  loading: boolean;
  sending?: boolean;
  onOpenTask?: (messageId: string) => void;
  onOpenTrace?: (taskId: string) => void;
  onSuggest?: (text: string, companyMode: boolean) => void;
  onGrillAnswer?: (messageId: string, answer: string, forceLock?: boolean) => void;
  onBattlePick?: (messageId: string, choice: string) => void;
}

const SUGGESTIONS: { text: string; company: boolean }[] = [
  { text: '用三句話介紹 EvoLoop', company: false },
  { text: '幫我寫本週工作報告大綱', company: true },
];

export default function MessageList({
  messages,
  sessionId,
  loading,
  onOpenTask,
  onOpenTrace,
  onSuggest,
  onGrillAnswer,
  onBattlePick,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-[13px] text-[#98989D]">載入對話…</p>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-8 py-20 text-center sm:py-28">
            <div>
              <h2 className="text-[20px] font-semibold tracking-tight text-[#F5F5F7] sm:text-[22px]">
                開始對話
              </h2>
              <p className="mt-2 text-[13px] text-[#98989D]">
                簡單任務即時生成 · 複雜任務多角色協作
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.text}
                  type="button"
                  onClick={() => onSuggest?.(s.text, s.company)}
                  className="rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-2 text-[12px] text-[#AEAEB2] transition-colors hover:border-white/[0.14] hover:text-[#F5F5F7]"
                >
                  {s.text}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            sessionId={sessionId}
            onOpenTask={msg.taskState ? () => onOpenTask?.(msg.id) : undefined}
            onOpenTrace={onOpenTrace}
            onGrillAnswer={onGrillAnswer}
            onBattlePick={onBattlePick}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
