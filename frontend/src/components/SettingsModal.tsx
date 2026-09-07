/** LLM 設定彈窗：快速加入 API。完整管理在控制台「系統 → API 路由」。 */
import ApiRoutesEditor from './ApiRoutesEditor';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
  onGoConsole?: () => void;
}

export default function SettingsModal({ open, onClose, onSaved, onGoConsole }: SettingsModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[#141416] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-5 py-3">
          <div>
            <p className="text-sm font-semibold text-[#F5F5F7]">API 分割</p>
            <p className="mt-0.5 text-[11px] text-[#8E8E93]">
              千問／DeepSeek／Kimi／OpenRouter 可同時存在；每組 API 再選多個模型
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

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <ApiRoutesEditor onChanged={onSaved} />
        </div>

        <div className="flex shrink-0 items-center justify-between border-t border-white/[0.06] px-5 py-3">
          <p className="text-[11px] text-[#636366]">角色模型與 Token 在「執行 → 角色 → 模型／路由」</p>
          {onGoConsole && (
            <button
              type="button"
              onClick={onGoConsole}
              className="rounded-lg px-3 py-1.5 text-[12px] font-medium text-[#64D2FF] hover:bg-[#007AFF]/10"
            >
              前往控制台
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
