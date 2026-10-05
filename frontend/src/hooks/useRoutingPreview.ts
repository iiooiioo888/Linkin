import { useEffect, useRef, useState } from 'react';
import { fetchRoutingPreview } from '../api/client';
import type { CompanyTemplate, RoutingPreview, RoutingPreviewMode } from '../types';

const DEBOUNCE_MS = 320;

/**
 * 輸入 debounce 後呼叫 POST /routing/preview；空字串與失敗不展示、不阻擋發送。
 */
export function useRoutingPreview(
  query: string,
  mode: RoutingPreviewMode,
  companyTemplate: CompanyTemplate,
): { preview: RoutingPreview | null; loading: boolean } {
  const [preview, setPreview] = useState<RoutingPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setPreview(null);
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
        .then((result) => {
          if (seq !== seqRef.current) return;
          setPreview(result);
        })
        .catch(() => {
          if (seq !== seqRef.current) return;
          setPreview(null);
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

  return { preview, loading };
}
