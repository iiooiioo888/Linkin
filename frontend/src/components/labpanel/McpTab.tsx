/**
 * MCP 分頁：依功能分組的工具開關，變更即儲存到目前登入帳號。
 */
import { MCP_FUNCTIONS, type McpTool } from './constants';

export function McpTab({
  tools,
  toolStatus,
  persistTools,
}: {
  tools: McpTool[];
  toolStatus: string | null;
  persistTools: (next: McpTool[]) => void;
}) {
  return (
          <div className="mx-auto max-w-2xl space-y-3">
            <p className="text-[11px] text-[var(--console-sub)]">
              開關按功能排列，並儲存到目前登入帳號。工業接線與採集相關開關見本頁各功能分組。
            </p>
            {toolStatus ? <p className="text-[11px] text-[var(--console-accent)]">{toolStatus}</p> : null}
            {MCP_FUNCTIONS.map((fn) => (
              <section key={fn} className="space-y-2">
                <h3 className="text-[11px] font-semibold tracking-wide text-[var(--console-faint)]">{fn}</h3>
                {tools
                  .filter((t) => t.fn === fn)
                  .map((t) => (
                    <label
                      key={t.id}
                      className="apple-card apple-card--tight flex cursor-pointer items-center gap-4 px-4 py-3"
                    >
                      <input
                        type="checkbox"
                        checked={t.enabled}
                        onChange={() =>
                          persistTools(tools.map((x) => (x.id === t.id ? { ...x, enabled: !x.enabled } : x)))
                        }
                        className="h-4 w-4 accent-[var(--console-accent)]"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-[13px] font-bold text-[var(--console-ink)]">{t.name}</p>
                        <p className="mt-0.5 text-[11px] text-[var(--console-sub)]">{t.desc}</p>
                      </div>
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                        style={{
                          color:
                            t.risk === 'high' ? 'var(--console-danger)' : t.risk === 'mid' ? 'var(--console-amber)' : 'var(--console-green)',
                          background:
                            t.risk === 'high'
                              ? 'rgba(255,59,48,0.12)'
                              : t.risk === 'mid'
                                ? 'rgba(255,149,0,0.12)'
                                : 'rgba(52,199,89,0.12)',
                        }}
                      >
                        {t.risk}
                      </span>
                    </label>
                  ))}
              </section>
            ))}
          </div>
  );
}
