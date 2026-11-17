/**
 * 上下文壓縮。倉庫沒有壓縮 HTTP API，畫面只標出缺口。
 */
import {
  GAP_LEAD,
  MISSING_COMPRESSION_APIS,
  NEARBY_ROUTES,
} from './gap';

export function ContextCompressionPage() {
  return (
    <section
      className="flex h-full min-h-0 flex-col apple-canvas text-[var(--console-ink)]"
      aria-labelledby="context-compression-heading"
      data-testid="context-compression"
    >
      <header className="border-b border-[var(--console-line)] px-4 py-3">
        <h1 id="context-compression-heading" className="l0-title">
          上下文壓縮
        </h1>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-[68ch]">
          <p role="status" className="text-[13px] leading-normal text-[var(--console-sub)]">
            {GAP_LEAD}
          </p>

          <h2 className="mt-6 text-[13px] font-medium text-[var(--console-ink)]">缺少的 API</h2>
          <ul className="mt-2 space-y-1">
            {MISSING_COMPRESSION_APIS.map((name) => (
              <li key={name}>
                <code className="apple-data text-[12px] text-[var(--console-sub)]">{name}</code>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12px] leading-normal text-[var(--console-faint)]">
            以上是規則截斷，不經模型。沒有把它們暴露出來的 HTTP 路由。
          </p>

          <h2 className="mt-6 text-[13px] font-medium text-[var(--console-ink)]">現有路由做的事</h2>
          <ul className="mt-2 space-y-2">
            {NEARBY_ROUTES.map((item) => (
              <li key={item.route} className="text-[13px] leading-normal text-[var(--console-sub)]">
                <code className="apple-data text-[12px] text-[var(--console-ink)]">{item.route}</code>
                <span className="mt-0.5 block text-[12px] text-[var(--console-faint)]">{item.does}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
