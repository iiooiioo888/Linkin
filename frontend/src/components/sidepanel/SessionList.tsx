/**
 * SidePanel 對話會話列表。
 */
import { useEffect, useState } from 'react';
import type { ChatSession } from '../../types';

function formatRelative(ts: number): string {
  const diff = Date.now() - ts;
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return '剛剛';
  if (minutes < 60) return `${minutes} 分鐘前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小時前`;
  return new Date(ts).toLocaleDateString('zh-TW');
}

export function SessionList({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}: {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
}) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  useEffect(() => {
    if (!confirmingId) return;
    const timer = setTimeout(() => setConfirmingId(null), 3000);
    return () => clearTimeout(timer);
  }, [confirmingId]);

  return (
    <>
      <div className="border-b border-white/[0.06] p-2.5">
        <p className="mb-2 px-0.5 text-[10px] font-bold text-[var(--console-sub)]">對話</p>
        <button
          onClick={onNewSession}
          className="w-full rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-[12px] font-medium text-[var(--console-ink)] transition-colors hover:bg-white/[0.06]"
        >
          新對話
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5">
        {sessions.length === 0 && (
          <p className="mt-8 px-3 text-center text-[11px] text-[var(--console-sub)]">尚無對話紀錄</p>
        )}
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group mb-0.5 flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 transition-colors ${
              session.id === activeSessionId
                ? 'bg-white/[0.06] text-[var(--console-ink)]'
                : 'text-[var(--console-sub)] hover:bg-white/[0.03] hover:text-[var(--console-ink)]'
            }`}
            onClick={() => onSelectSession(session.id)}
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-[var(--console-ink)]">
                {session.title || '新對話'}
              </p>
              <p className="text-[10px] text-[var(--console-sub)]">{formatRelative(session.updatedAt)}</p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (confirmingId === session.id) {
                  onDeleteSession(session.id);
                  setConfirmingId(null);
                } else {
                  setConfirmingId(session.id);
                }
              }}
              className={`shrink-0 rounded-lg px-1.5 py-1 text-[10px] transition-all ${
                confirmingId === session.id
                  ? 'bg-[color-mix(in_srgb,var(--console-danger)_20%,transparent)] text-[var(--console-danger)] opacity-100'
                  : 'text-[var(--console-sub)] opacity-0 hover:bg-[color-mix(in_srgb,var(--console-danger)_15%,transparent)] hover:text-[var(--console-danger)] group-hover:opacity-100'
              }`}
              aria-label="刪除會話"
            >
              {confirmingId === session.id ? '確認?' : '刪'}
            </button>
          </div>
        ))}
      </div>
      <div className="border-t border-white/[0.06] px-3 py-2 text-[10px] text-[var(--console-faint)]">
        本機儲存
      </div>
    </>
  );
}
