/** 設定彈窗：只留對話需要的 API 設定，不連到角色、計費或控制台。 */
import ApiRoutesEditor from './ApiRoutesEditor';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

export default function SettingsModal({ open, onClose, onSaved }: SettingsModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/[0.08] bg-[var(--console-card)] shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-white/[0.06] px-5 py-3">
          <div>
            <p className="text-sm font-semibold text-[var(--console-ink)]">API 設定</p>
            <p className="mt-0.5 text-[11px] text-[var(--console-sub)]">加入供應商金鑰，對話才能送出</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-2 py-1 text-[var(--console-sub)] hover:bg-white/[0.06]"
            aria-label="關閉"
          >
            ✕
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <ApiRoutesEditor compact onChanged={onSaved} />
        </div>
      </div>
    </div>
  );
}
