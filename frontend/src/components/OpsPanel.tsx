/**
 * 基礎設施合併面板：AI Hub · 雲 · 檢查點 · 連接池。
 * API 路由已升為控制台一級頁面（配置 → API 路由）。
 */
import { useState } from 'react';
import CheckpointsPanel from './CheckpointsPanel';
import CloudConsoleView from './CloudConsoleView';
import DbPoolPanel from './DbPoolPanel';
import HubPanel from './HubPanel';

type OpsTab = 'hub' | 'cloud' | 'checkpoints' | 'dbpool';

export default function OpsPanel() {
  const [tab, setTab] = useState<OpsTab>('hub');

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas">
      <div className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-white/[0.06] px-6 py-3">
        {(
          [
            ['hub', 'AI Hub'],
            ['cloud', '雲端'],
            ['checkpoints', '檢查點'],
            ['dbpool', '連接池'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded-full px-3.5 py-1.5 text-[12px] font-bold transition-colors ${
              tab === key
                ? 'bg-[#007AFF] text-white'
                : 'bg-white/[0.04] text-[#AEAEB2] hover:text-[#F5F5F7]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        {tab === 'hub' && <HubPanel />}
        {tab === 'cloud' && <CloudConsoleView />}
        {tab === 'checkpoints' && <CheckpointsPanel />}
        {tab === 'dbpool' && <DbPoolPanel />}
      </div>
    </div>
  );
}
