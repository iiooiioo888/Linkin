import { useEffect, useRef, useState } from 'react';
import { fetchPathSuggestion, type PathSuggestion } from '../api/client';

const DEBOUNCE_MS = 320;

/** 輸入停頓後向建議端點詢問。失敗時不展示、不阻擋手動選擇。 */
export function usePathSuggestion(query: string): {
  suggestion: PathSuggestion | null;
  loading: boolean;
} {
  const [suggestion, setSuggestion] = useState<PathSuggestion | null>(null);
  const [loading, setLoading] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setSuggestion(null);
      setLoading(false);
      return;
    }
    const seq = ++seqRef.current;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      void fetchPathSuggestion(trimmed, controller.signal)
        .then((next) => {
          if (seq === seqRef.current) setSuggestion(next);
        })
        .catch(() => {
          if (seq === seqRef.current && !controller.signal.aborted) setSuggestion(null);
        })
        .finally(() => {
          if (seq === seqRef.current) setLoading(false);
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  return { suggestion, loading };
}
