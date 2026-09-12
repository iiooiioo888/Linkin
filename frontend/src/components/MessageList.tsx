/**
 * 訊息列表：居中窄欄，空態極簡。
 * 僅在新訊息／串流正文變化且貼近底部時自動捲動，避免決策列被進度輪詢搶點擊。
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ChatMessage, TaskProgress } from '../types';
import { dismissChatEmptyHint, isChatEmptyHintDismissed } from '../lib/onboarding';
import MessageBubble from './MessageBubble';

interface MessageListProps {
  messages: ChatMessage[];
  sessionId: string;
  loading: boolean;
  sending?: boolean;
  onOpenTask?: (messageId: string) => void;
  onOpenTrace?: (taskId: string) => void;
  /** 開啟對話底部詳細區 Context */
  onOpenContext?: (taskId: string) => void;
  onSuggest?: (text: string, companyMode: boolean) => void;
  onGrillAnswer?: (messageId: string, answer: string, forceLock?: boolean) => void;
  onBattlePick?: (messageId: string, choice: string) => void;
  onTaskStatePatch?: (taskId: string, patch: Partial<TaskProgress> | TaskProgress) => void;
  variant?: 'default' | 'drawer';
  /** 左右分裂時隱藏氣泡內看板，避免與右側監控重複 */
  hideTaskCard?: boolean;
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
  onOpenContext,
  onSuggest,
  onGrillAnswer,
  onBattlePick,
  onTaskStatePatch,
  variant = 'default',
  hideTaskCard = false,
}: MessageListProps) {
  const { t } = useTranslation();
  const [hintVisible, setHintVisible] = useState(() => !isChatEmptyHintDismissed());
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const prevLen = useRef(messages.length);
  const lastMsg = messages[messages.length - 1];
  const scrollKey = `${messages.length}:${lastMsg?.id ?? ''}:${lastMsg?.content?.length ?? 0}:${lastMsg?.streaming ? 1 : 0}`;

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const onScroll = () => {
      stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 96;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    const grew = messages.length > prevLen.current;
    prevLen.current = messages.length;
    if (!stickToBottom.current) return;
    if (grew || lastMsg?.streaming) {
      bottomRef.current?.scrollIntoView({ behavior: grew ? 'smooth' : 'auto' });
    }
  }, [scrollKey, messages.length, lastMsg?.streaming]);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <p className="text-[13px] text-[#98989D]">載入對話…</p>
      </div>
    );
  }

  return (
    <div ref={scrollerRef} className={`min-h-0 flex-1 overflow-y-auto ${variant === 'drawer' ? 'px-4 py-4' : 'px-4 py-5 sm:px-6'}`}>
      <div className={`flex flex-col gap-4 ${variant === 'drawer' ? '' : 'mx-auto w-full max-w-3xl'}`}>
        {messages.length === 0 && (
          <div className={`flex flex-col items-center gap-8 text-center ${variant === 'drawer' ? 'py-10' : 'py-20 sm:py-28'}`}>
            <div>
              <h2 className="text-[20px] font-semibold tracking-tight text-[#F5F5F7] sm:text-[22px]">
                {t('chat.emptyTitle')}
              </h2>
              <p className="mt-2 text-[13px] text-[#98989D]">
                {t('chat.emptySubtitle')}
              </p>
              {hintVisible && (
                <div className="mt-4 rounded-xl border border-[color-mix(in_srgb,var(--console-accent)_20%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_6%,transparent)] px-4 py-3 text-left">
                  <p className="text-[12px] text-[var(--console-sub)]">{t('chat.emptyPipelineHint')}</p>
                  <button
                    type="button"
                    className="mt-2 text-[11px] text-[var(--console-accent)] hover:underline"
                    onClick={() => {
                      dismissChatEmptyHint();
                      setHintVisible(false);
                    }}
                  >
                    {t('common.dismiss')}
                  </button>
                </div>
              )}
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
            onOpenContext={onOpenContext}
            onGrillAnswer={onGrillAnswer}
            onBattlePick={onBattlePick}
            onTaskStatePatch={onTaskStatePatch}
            variant={variant === 'drawer' || hideTaskCard ? 'workspace' : 'default'}
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

