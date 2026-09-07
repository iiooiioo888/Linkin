/**
 * Mermaid 圖表渲染 — 用於資金流瀑布／狀態機視圖。
 */
import { useEffect, useId, useRef, useState } from 'react';

export default function MermaidBlock({ chart, title }: { chart: string; title?: string }) {
  const rawId = useId().replace(/:/g, '');
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    if (!chart.trim() || !containerRef.current) return;

    void (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'neutral',
          securityLevel: 'strict',
          flowchart: { htmlLabels: true, curve: 'basis' },
        });
        const { svg } = await mermaid.render(`mmd-${rawId}`, chart);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [chart, rawId]);

  async function copySource() {
    try {
      await navigator.clipboard.writeText(chart);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="cf-mermaid">
      {title ? (
        <div className="cf-mermaid-head">
          <h3 className="cf-mermaid-title">{title}</h3>
          <button type="button" className="sq-tree-chip" onClick={() => void copySource()}>
            {copied ? '已複製' : '複製 Mermaid'}
          </button>
        </div>
      ) : null}
      {error ? (
        <>
          <p className="cf-mermaid-err">{error}</p>
          <pre className="cf-mermaid-fallback">{chart}</pre>
        </>
      ) : (
        <div ref={containerRef} className="cf-mermaid-svg" role="img" aria-label={title ?? 'Mermaid 圖表'} />
      )}
    </div>
  );
}
