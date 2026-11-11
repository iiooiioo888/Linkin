/**
 * ChatView 頂部通知橫幅：未配置 API／錯誤／操作錯誤。
 */
import type { Dispatch, SetStateAction } from 'react';
import ErrorState from '../ui/ErrorState';

interface ChatNoticesProps {
  llmConfigured?: boolean | null;
  onOpenSettings?: () => void;
  error: string | null;
  lastQuery: string | null;
  onRetry: () => void;
  onDismissError: () => void;
  actError: string | null;
  setActError: Dispatch<SetStateAction<string | null>>;
}

export function ChatNotices({
  llmConfigured,
  onOpenSettings,
  error,
  lastQuery,
  onRetry,
  onDismissError,
  actError,
  setActError,
}: ChatNoticesProps) {
  return (
    <>
    {llmConfigured === false && (
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[color-mix(in_srgb,var(--console-amber)_20%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_8%,transparent)] px-4 py-2 sm:px-6">
        <p className="text-[12px] text-[var(--console-amber)]">尚未配置 API。請先加入千問／DeepSeek／Kimi／OpenRouter。</p>
        {onOpenSettings && (
          <button
            type="button"
            onClick={onOpenSettings}
            className="shrink-0 rounded-lg bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)] px-2.5 py-1 text-[11px] font-medium text-[var(--console-amber)] hover:bg-[color-mix(in_srgb,var(--console-amber)_25%,transparent)]"
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
    {actError && (
      <div className="shrink-0 px-4 pt-3 sm:px-6">
        <ErrorState kind="generic" message={actError} compact onDismiss={() => setActError(null)} />
      </div>
    )}
    </>
  );
}
