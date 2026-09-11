/**
 * HubPanel — AI Hub 統一面板（操作台 + 監控）。
 */
import { useState } from 'react';
import HubMonitorPanel from './HubMonitorPanel';
import HubView from './HubView';
import { ConsoleCard, ConsoleCardBody, ConsoleCardHeader } from './ui/ConsoleLayout';

type HubMode = 'console' | 'monitor';

const MODES: { key: HubMode; icon: string; label: string }[] = [
  { key: 'console', icon: '🎛️', label: '操作台' },
  { key: 'monitor', icon: '📡', label: '監控' },
];

export default function HubPanel({ embedded = false }: { embedded?: boolean }) {
  const [mode, setMode] = useState<HubMode>('console');

  if (embedded) {
    return (
      <div className="space-y-3">
        <ConsoleCard>
          <ConsoleCardHeader>操作台</ConsoleCardHeader>
          <ConsoleCardBody dense>
            <HubView embedded />
          </ConsoleCardBody>
        </ConsoleCard>
        <ConsoleCard>
          <ConsoleCardHeader>監控</ConsoleCardHeader>
          <ConsoleCardBody dense>
            <HubMonitorPanel embedded />
          </ConsoleCardBody>
        </ConsoleCard>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
      <div className="flex shrink-0 items-center gap-1 border-b border-white/[0.08] bg-[#1C1C1E] px-3 py-2">
        <span className="mr-2 text-xs font-semibold text-[#64D2FF]">🛰️ AI Hub</span>
        {MODES.map((item) => {
          const active = mode === item.key;
          return (
            <button
              key={item.key}
              type="button"
              onClick={() => setMode(item.key)}
              className={`rounded-md border px-2.5 py-1 text-[11px] transition-colors ${
                active
                  ? 'border-[#007AFF]/50 bg-[#007AFF]/15 text-[#64D2FF]'
                  : 'border-white/[0.08] text-[#8a8f98] hover:text-[#d0d6e0]'
              }`}
            >
              {item.icon} {item.label}
            </button>
          );
        })}
        <p className="ml-auto hidden text-[10px] text-[#62666d] sm:block">
          GPT-5.6 Sol · Gemini 3.1 Pro · 零 Claude
        </p>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {mode === 'console' ? <HubView embedded /> : <HubMonitorPanel />}
      </div>
    </div>
  );
}
