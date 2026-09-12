/**
 * AI 可見事件 — 人類與 AI 共用同一事件源。
 */
import { MiniProgressBar } from '../../../components/ui/monitor';
import { ConsoleCard, ConsoleCardHeader } from '../../../components/ui/ConsoleLayout';
import { formatTs, statusLabel, statusStripe, useAiEvents } from './shared';

export default function AiEventsPanel({ compact = false }: { compact?: boolean }) {
  const { events, error, reload } = useAiEvents(compact ? 8 : 24);

  return (
    <ConsoleCard className={compact ? '' : 'mt-3'}>
      <div className="flex items-center justify-between gap-2 border-b border-[var(--console-border)] px-3 py-2">
        <ConsoleCardHeader className="border-0 p-0">AI 可見事件</ConsoleCardHeader>
        <button type="button" className="console-btn-ghost text-xs" onClick={() => void reload()}>
          刷新
        </button>
      </div>
      <p className="px-3 pt-1 text-[9px] text-[var(--console-faint)]">與 /linkin/minecraft/ai/events 同步</p>
      {error ? <p className="console-status-red px-3 pb-3 text-xs">{error}</p> : null}
      {!events.length ? (
        <div className="px-3 pb-3 text-xs text-[var(--console-faint)]">
          <p>尚無事件 — 執行敘事／建築／地圖操作後會出現。</p>
          <a href="#/modules/minecraft/narrative" className="mt-2 inline-block text-[var(--console-accent)] hover:underline">
            前往敘事工作區 →
          </a>
        </div>
      ) : (
        <ul className="divide-y divide-[var(--console-border)] px-1 pb-2">
          {events.map((evt) => {
            const stripe = statusStripe(evt.status);
            return (
              <li key={evt.id} className="mon-task-card flex gap-2 px-2 py-2 text-xs" data-priority={stripe}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[10px] text-[var(--console-faint)]">{formatTs(evt.ts)}</span>
                    <span className="rounded bg-[var(--console-card)] px-1.5 py-0.5 text-[10px]">
                      {evt.domain}/{evt.action}
                    </span>
                    <span className="text-[var(--console-accent)]">{statusLabel(evt.status)}</span>
                    {evt.dry_run ? <span className="text-[var(--console-amber)]">dry-run</span> : null}
                    {evt.bridge_offline ? <span className="text-[var(--console-red)]">bridge_offline</span> : null}
                  </div>
                  <p className="mt-1 text-[var(--console-text)]">{evt.summary}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {!compact ? (
        <div className="border-t border-[var(--console-border)] px-3 py-2">
          <p className="mb-1 text-[9px] text-[var(--console-faint)]">事件密度</p>
          <MiniProgressBar value={Math.min(100, events.length * 8)} />
        </div>
      ) : null}
    </ConsoleCard>
  );
}
