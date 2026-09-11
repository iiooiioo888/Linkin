/**
 * 統一錯誤／異常狀態。
 */
import type { ReactNode } from 'react';

export type ErrorKind = 'opc_guard' | 'llm' | 'network' | 'partial' | 'generic';

const TONE: Record<ErrorKind, { title: string; color: string }> = {
  opc_guard: { title: 'OPC 護欄', color: 'var(--console-amber)' },
  llm: { title: '模型失敗', color: 'var(--console-danger)' },
  network: { title: '連線異常', color: 'var(--console-danger)' },
  partial: { title: '部分來源', color: 'var(--console-amber)' },
  generic: { title: '錯誤', color: 'var(--console-danger)' },
};

export default function ErrorState({
  kind = 'generic',
  message,
  detail,
  onRetry,
  onDismiss,
  compact,
}: {
  kind?: ErrorKind;
  message: string;
  detail?: ReactNode;
  onRetry?: () => void;
  onDismiss?: () => void;
  compact?: boolean;
}) {
  const tone = TONE[kind];
  return (
    <div
      role="alert"
      className={`rounded-xl border px-3.5 ${compact ? 'py-2' : 'py-3'} ${
        kind === 'opc_guard' || kind === 'partial'
          ? 'border-[#FF9F0A]/20 bg-[#FF9F0A]/8'
          : 'border-[#FF453A]/20 bg-[#FF453A]/8'
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span className="apple-dot mt-1.5 shrink-0" style={{ background: tone.color }} />
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-medium" style={{ color: tone.color }}>
            {tone.title}
          </p>
          <p className="mt-0.5 text-[13px] leading-snug text-[var(--console-ink)]">{message}</p>
          {detail && <div className="mt-1.5 text-[11px] text-[#98989D]">{detail}</div>}
          {(onRetry || onDismiss) && (
            <div className="mt-2 flex gap-2">
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="rounded-lg bg-[#0A84FF] px-2.5 py-1 text-[11px] font-medium text-white"
                >
                  重試
                </button>
              )}
              {onDismiss && (
                <button
                  type="button"
                  onClick={onDismiss}
                  className="rounded-lg px-2.5 py-1 text-[11px] text-[#98989D] hover:text-[var(--console-ink)]"
                >
                  關閉
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
