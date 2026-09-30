/**
 * AI 可見事件 — 與後端同一事件源，不畫假密度。
 */
import { McPanel } from '../McChrome';
import { formatTs, playerActionLabel, statusLabel, statusStripe, useAiEvents } from './shared';
import '../minecraft.css';

export default function AiEventsPanel({ compact = false }: { compact?: boolean }) {
  const { events, error, reload } = useAiEvents(compact ? 8 : 24);

  return (
    <McPanel
      title="可見事件"
      action={
        <button type="button" className="rd-btn" onClick={() => void reload()}>
          重新整理
        </button>
      }
    >
      {error ? <p className="mc-error">{error}</p> : null}
      {!error && !events.length ? (
        <p className="mc-empty">敘事、建築或地圖操作之後，事件會出現在這裡。</p>
      ) : null}
      {events.length ? (
        <ul className="divide-y divide-[var(--console-border)] px-1 pb-2">
          {events.map((evt) => {
            const stripe = statusStripe(evt.status);
            return (
              <li key={evt.id} className="mon-task-card flex gap-2 px-2 py-2 text-[13px]" data-priority={stripe}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[12px] text-[var(--console-faint)]">{formatTs(evt.ts)}</span>
                    <span className="rounded bg-[var(--console-card)] px-1.5 py-0.5 text-[12px]">
                      {evt.domain === 'player' ? playerActionLabel(evt.action) : `${evt.domain}/${evt.action}`}
                    </span>
                    <span className="text-[var(--console-accent)]">{statusLabel(evt.status)}</span>
                    {evt.dry_run ? <span className="text-[var(--console-amber)]">乾跑</span> : null}
                    {evt.bridge_offline ? <span className="text-[var(--console-red)]">橋接離線</span> : null}
                  </div>
                  <p className="mt-1 text-[var(--console-text)]">{evt.summary}</p>
                </div>
              </li>
            );
          })}
        </ul>
      ) : null}
    </McPanel>
  );
}
