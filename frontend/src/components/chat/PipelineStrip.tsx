/**
 * 對話側精簡管線條 — 僅顯示階段進度，取代進行中任務的密集監控台。
 */
import { useTranslation } from 'react-i18next';
import type { TaskProgress } from '../../types';
import { COMPANY_PHASES, OPC_PHASES, STANDARD_PHASES } from '../TaskPanel';

interface PipelineStripProps {
  task: TaskProgress;
  onPinMonitor?: () => void;
  pinned?: boolean;
}

function phasesFor(task: TaskProgress) {
  if (task.resolved_path === 'opc') return OPC_PHASES;
  if (task.resolved_path === 'company') return COMPANY_PHASES;
  return STANDARD_PHASES;
}

export default function PipelineStrip({ task, onPinMonitor, pinned }: PipelineStripProps) {
  const { t } = useTranslation();
  const phases = phasesFor(task);
  const currentIdx = phases.findIndex((p) => p.key === task.phase);
  const idx = currentIdx >= 0 ? currentIdx : 0;

  return (
    <div
      className="mx-4 mb-2 shrink-0 rounded-xl border border-[color-mix(in_srgb,var(--console-accent)_25%,transparent)] bg-[var(--console-card)] px-3 py-2 sm:mx-6"
      data-testid="chat-pipeline-strip"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-[var(--console-accent)]">
          {t('chat.pipelineRunning')}
        </p>
        {onPinMonitor && (
          <button
            type="button"
            onClick={onPinMonitor}
            className={`rounded-md px-2 py-0.5 text-[10px] transition-colors ${
              pinned
                ? 'bg-[color-mix(in_srgb,var(--console-accent)_18%,transparent)] text-[var(--console-accent)]'
                : 'text-[var(--console-sub)] hover:bg-white/[0.04] hover:text-[var(--console-ink)]'
            }`}
            title={t('chat.pinMonitor')}
          >
            {pinned ? t('chat.monitorPinned') : t('chat.pinMonitor')}
          </button>
        )}
      </div>
      <ol className="flex items-center gap-1 overflow-x-auto pb-0.5 [-webkit-overflow-scrolling:touch] [scrollbar-width:none]">
        {phases.map((phase, i) => {
          const done = i < idx;
          const active = i === idx;
          return (
            <li key={phase.key} className="flex shrink-0 items-center gap-1">
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium whitespace-nowrap ${
                  active
                    ? 'bg-[color-mix(in_srgb,var(--console-accent)_20%,transparent)] text-[var(--console-accent)] ring-1 ring-[color-mix(in_srgb,var(--console-accent)_40%,transparent)]'
                    : done
                      ? 'bg-[color-mix(in_srgb,var(--console-green)_12%,transparent)] text-[var(--console-green)]'
                      : 'bg-white/[0.04] text-[var(--console-faint)]'
                }`}
              >
                {phase.label}
              </span>
              {i < phases.length - 1 && (
                <span className="text-[8px] text-[var(--console-faint)]" aria-hidden>›</span>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
