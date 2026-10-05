import { useEffect, useRef, useState } from 'react';
import { fetchRoutingPreview } from '../api/client';
import type { RoutingPreviewSnapshot } from '../lib/routingPreview';
import type { CompanyTemplate, RoutingPreviewMode } from '../types';

const DEBOUNCE_MS = 320;

/**
 * 輸入 debounce 後呼叫 POST /routing/preview；空字串與失敗不展示、不阻擋發送。
 * snapshot 含 query／mode／template，供發送時比對是否仍有效。
 */
export function useRoutingPreview(
  query: string,
  mode: RoutingPreviewMode,
  companyTemplate: CompanyTemplate,
): { snapshot: RoutingPreviewSnapshot | null; loading: boolean } {
  const [snapshot, setSnapshot] = useState<RoutingPreviewSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setSnapshot(null);
      setLoading(false);
      return;
    }

    const seq = ++seqRef.current;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      void fetchRoutingPreview(
        {
          query: trimmed,
          mode,
          company_template: mode === 'company' ? companyTemplate : undefined,
        },
        controller.signal,
      )
        .then((preview) => {
          if (seq !== seqRef.current) return;
          setSnapshot({
            query: trimmed,
            mode,
            companyTemplate,
            preview,
          });
        })
        .catch(() => {
          if (seq !== seqRef.current) return;
          setSnapshot(null);
        })
        .finally(() => {
          if (seq !== seqRef.current) return;
          setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, mode, companyTemplate]);

  return { snapshot, loading };
}
