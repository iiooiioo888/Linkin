/**
 * Monaco Editor 包裝 — 角色 system prompt 編輯（深色 IDE 風格）。
 */
import Editor from '@monaco-editor/react';

export default function PromptEditor({
  value,
  onChange,
  height = 220,
  readOnly = false,
  language = 'markdown',
}: {
  value: string;
  onChange?: (next: string) => void;
  height?: number | string;
  readOnly?: boolean;
  language?: string;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-[var(--console-card)]">
      <Editor
        height={height}
        language={language}
        theme="vs-dark"
        value={value}
        onChange={(v) => onChange?.(v ?? '')}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 12,
          lineHeight: 18,
          fontFamily: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
          scrollBeyondLastLine: false,
          wordWrap: 'on',
          padding: { top: 12, bottom: 12 },
          renderLineHighlight: 'line',
          overviewRulerLanes: 0,
          hideCursorInOverviewRuler: true,
          scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
          tabSize: 2,
        }}
        loading={
          <div className="flex h-full items-center justify-center text-[12px] text-[var(--console-sub)]">
            載入編輯器…
          </div>
        }
      />
    </div>
  );
}
