/**
 * HubPanel — AI Hub 統一面板（操作台 + 監控），分頁切換無滾動。
 */
import { useState } from 'react';
import HubMonitorPanel from './HubMonitorPanel';
import HubView from './HubView';
import { ConsolePageFrame } from './ui/ConsolePagination';
import { ConsoleSectionNav } from './ui/ConsoleLayout';
import { useFixedPages } from '../lib/pagination';

type HubMode = 'console' | 'monitor';

const MODES: { id: string; key: HubMode; label: string }[] = [
  { id: 'hub-console', key: 'console', label: '操作台' },
  { id: 'hub-monitor', key: 'monitor', label: '監控' },
];

export default function HubPanel({ embedded = false }: { embedded?: boolean }) {
  const [mode, setMode] = useState<HubMode>('console');
  const activeId = MODES.find((m) => m.key === mode)?.id ?? MODES[0].id;

  if (embedded) {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ConsoleSectionNav
          sections={MODES.map((m) => ({ id: m.id, label: m.label }))}
          activeId={activeId}
          onSelect={(id) => {
            const next = MODES.find((m) => m.id === id);
            if (next) setMode(next.key);
          }}
          className="!static !z-0 !border-0 !bg-transparent !px-0 !py-0 !backdrop-blur-none"
        />
        <div className="min-h-0 flex-1 overflow-hidden">
          {mode === 'console' ? <HubView embedded /> : <HubMonitorPanel embedded />}
        </div>
      </div>
    );
  }

  const { page, pages, setPage } = useFixedPages(1);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.08] bg-[var(--console-card)] px-3 py-2">
        <span className="mr-2 text-xs font-semibold console-status-blue">🛰️ AI Hub</span>
        {MODES.map((item) => {
          const active = mode === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setMode(item.key)}
              className={`rounded-md border px-2.5 py-1 text-[11px] transition-colors ${
                active
                  ? 'border-[var(--console-blue)]/50 bg-[var(--console-blue)]/15 console-status-blue'
                  : 'border-white/[0.08] text-[var(--console-sub)] hover:text-[#d0d6e0]'
              }`}
            >
              {item.label}
            </button>
          );
        })}
        <p className="ml-auto hidden text-[10px] text-[var(--console-faint)] sm:block">
          GPT-5.6 Sol · Gemini 3.1 Pro · 零 Claude
        </p>
      </div>
      <ConsolePageFrame page={page} totalPages={pages} onPageChange={setPage}>
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          {mode === 'console' ? <HubView embedded /> : <HubMonitorPanel />}
        </div>
      </ConsolePageFrame>
    </div>
  );
}
