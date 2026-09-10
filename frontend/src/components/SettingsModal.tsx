/** 設定彈窗：快速加入 API，並接到控制台角色／用量。 */
import { navPathForTab } from '../lib/monitorTabs';
import { requestRoleSettingsDesk } from '../lib/agentUi';
import ApiRoutesEditor from './ApiRoutesEditor';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  onGoConsole?: () => void;
  onGoAgents?: () => void;
  onGoUsage?: () => void;
}

export default function SettingsModal({
  open,
  onClose,
  onSaved,
  onGoConsole,
  onGoAgents,
  onGoUsage,
}: SettingsModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#141416] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-5 py-3">
          <div>
            <p className="text-sm font-semibold text-[#F5F5F7]">API 與角色</p>
            <p className="mt-0.5 text-[11px] text-[#8E8E93]">
              先加入供應商，再到每個角色指定模型與 Token
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-[#8E8E93] hover:bg-white/[0.06]"
            aria-label="關閉"
          >
            ✕
          </button>
        </div>

        <div className="grid shrink-0 grid-cols-3 gap-px border-b border-white/[0.06] bg-white/[0.06]">
          <div className="bg-[#141416] px-3 py-2">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#64D2FF]">1 配置</p>
            <p className="text-[11px] text-[#AEAEB2]">千問／DeepSeek／Kimi／OpenRouter</p>
          </div>
          <button
            type="button"
            className="bg-[#141416] px-3 py-2 text-left hover:bg-white/[0.03]"
            onClick={() => {
              requestRoleSettingsDesk();
              onGoAgents?.();
            }}
          >
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#636366]">2 角色</p>
            <p className="text-[11px] text-[#AEAEB2]">模型與 Token</p>
          </button>
          <button
            type="button"
            className="bg-[#141416] px-3 py-2 text-left hover:bg-white/[0.03]"
            onClick={() => onGoUsage?.()}
          >
            <p className="text-[10px] font-bold uppercase tracking-wider text-[#636366]">3 計費</p>
            <p className="text-[11px] text-[#AEAEB2]">AI 用量與 Docker 成本</p>
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <ApiRoutesEditor compact onChanged={onSaved} />
        </div>

        <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] px-5 py-3">
          <p className="text-[11px] text-[#636366]">
            完整管理在「{navPathForTab('llm')}」
          </p>
          <div className="flex flex-wrap gap-2">
            {onGoAgents && (
              <button
                type="button"
                onClick={() => {
                  requestRoleSettingsDesk();
                  onGoAgents();
                }}
                className="rounded-lg px-3 py-1.5 text-[12px] font-medium text-[#AEAEB2] hover:bg-white/[0.06]"
              >
                {navPathForTab('agents')}
              </button>
            )}
            {onGoConsole && (
              <button
                type="button"
                onClick={onGoConsole}
                className="rounded-lg px-3 py-1.5 text-[12px] font-medium text-[#64D2FF] hover:bg-[#007AFF]/10"
              >
                {navPathForTab('llm')}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
