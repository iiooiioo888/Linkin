/**
 * 整合面板共用小元件：錯誤／成功提示條與 JSON 區塊。
 */
export function ErrorBar({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-3 rounded-md border border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-3 py-2 text-xs console-status-danger">
      {message}
    </div>
  );
}

export function OkBar({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs console-status-green">
      {message}
    </div>
  );
}

export function JsonBlock({ value }: { value: unknown }) {
  if (value == null) return null;
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-white/[0.06] bg-black/40 p-2 text-[10px] leading-relaxed text-[var(--console-sub)]">
      {text}
    </pre>
  );
}
