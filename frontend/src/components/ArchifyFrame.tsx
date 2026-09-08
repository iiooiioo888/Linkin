/**
 * 嵌入 tt-a1i/archify CLI 產出的獨立 HTML。
 * 開發時走 Vite 外掛（npm 依賴 archify）；正式環境走後端 /lab/archify/*。
 */
import { useEffect, useRef, useState } from 'react';
import {
  labArchifyArtifactUrl,
  labArchifyDevRender,
  labArchifyHtml,
  labArchifyRender,
  type ArchifyIR,
} from '../api/client';
import ArchifyViewer from './ArchifyViewer';

async function loadArchifyHtml(opts: {
  html?: string | null;
  ir?: ArchifyIR | null;
  view?: string;
  id?: string;
  kind?: string;
}): Promise<string> {
  if (opts.html) return opts.html;
  const ir = opts.ir ?? null;

  if (ir && import.meta.env.DEV) {
    try {
      const row = await labArchifyDevRender(ir);
      if (row.html && /<svg/i.test(row.html)) return row.html;
    } catch {
      /* Vite 外掛尚未就緒時改走後端 */
    }
  }

  if (opts.view) {
    try {
      const row = await labArchifyHtml({ view: opts.view, id: opts.id, kind: opts.kind });
      if (row.html && /<svg/i.test(row.html)) return row.html;
    } catch {
      /* 舊後端沒有 /lab/archify/html */
    }
    try {
      const resp = await fetch(labArchifyArtifactUrl({ view: opts.view, id: opts.id, kind: opts.kind }));
      const type = resp.headers.get('content-type') || '';
      if (resp.ok && type.includes('text/html')) {
        const text = await resp.text();
        if (/<svg/i.test(text)) return text;
      }
    } catch {
      /* artifact 404 會是 JSON，不能當 iframe */
    }
  }

  if (ir) {
    try {
      const row = await labArchifyDevRender(ir);
      if (row.html && /<svg/i.test(row.html)) return row.html;
    } catch {
      /* 生產靜態站沒有 Vite 外掛 */
    }
    const row = await labArchifyRender(ir);
    if (row.html && /<svg/i.test(row.html)) return row.html;
  }

  throw new Error('Archify 沒有回傳 HTML');
}

export default function ArchifyFrame({
  html,
  ir,
  view,
  id,
  kind,
  fallbackIr,
  focusId,
  onSelect,
  compact = false,
}: {
  html?: string | null;
  ir?: ArchifyIR | null;
  view?: string;
  id?: string;
  kind?: string;
  fallbackIr?: ArchifyIR | null;
  focusId?: string | null;
  onSelect?: (nodeId: string) => void;
  compact?: boolean;
}) {
  const [blobSrc, setBlobSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const urlRef = useRef<string | null>(null);
  const renderIr = ir ?? fallbackIr ?? null;
  const irKey = renderIr
    ? `${renderIr.meta?.type ?? ''}:${renderIr.meta?.title ?? ''}:${renderIr.nodes?.length ?? 0}`
    : '';

  useEffect(() => {
    let cancelled = false;

    function revoke() {
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current);
        urlRef.current = null;
      }
    }

    if (!html && !renderIr && !view) {
      setLoading(false);
      setError('沒有可渲染的圖');
      setBlobSrc(null);
      return () => {
        cancelled = true;
        revoke();
      };
    }

    setLoading(true);
    setError(null);

    void loadArchifyHtml({ html, ir: renderIr, view, id, kind })
      .then((nextHtml) => {
        if (cancelled) return;
        revoke();
        const url = URL.createObjectURL(new Blob([nextHtml], { type: 'text/html;charset=utf-8' }));
        urlRef.current = url;
        setBlobSrc(url);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        revoke();
        setBlobSrc(null);
        setError((err as Error).message);
        setLoading(false);
      });

    return () => {
      cancelled = true;
      revoke();
    };
    // irKey 代表同一張圖；不要依 renderIr 物件身分重繪（回測曲線更新會換新物件）。
  }, [html, id, irKey, kind, view]);

  const fallback = renderIr;
  const fallbackSvg =
    fallback?.nodes?.length ? (
      <ArchifyViewer ir={fallback} focusId={focusId} onSelect={onSelect} compact={compact} />
    ) : null;

  return (
    <div className="archify-stack">
      {blobSrc ? (
        <div className="apple-card apple-card--diagram archify-frame-card">
          <iframe
            key={blobSrc}
            className="archify-frame"
            title="Archify"
            sandbox="allow-scripts"
            src={blobSrc}
          />
        </div>
      ) : (
        fallbackSvg
      )}
      {!blobSrc && !fallbackSvg ? (
        loading ? (
          <p className="py-8 text-center text-[12px] text-[#8E8E93]">Archify 繪製中…</p>
        ) : (
          <p className="py-8 text-center text-[11px] text-[#636366]">{error || '沒有圖表'}</p>
        )
      ) : null}
      {blobSrc && loading ? (
        <p className="px-1 text-[10px] text-[#8E8E93]">Archify 繪製中…</p>
      ) : null}
      {error && fallbackSvg && !blobSrc ? (
        <p className="px-1 text-[10px] text-[#8E8E93]">Archify CLI：{error}</p>
      ) : null}
    </div>
  );
}
