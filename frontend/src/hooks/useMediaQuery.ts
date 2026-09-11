import { useEffect, useState } from 'react';

/** 訂閱 matchMedia，SSR 時回傳 fallback（預設 false）。 */
export function useMediaQuery(query: string, fallback = false): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return fallback;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [query]);

  return matches;
}

/** Tailwind `md` 斷點：≥768px 視為桌面 IDE 布局。 */
export function useIsDesktop(): boolean {
  return useMediaQuery('(min-width: 768px)', true);
}
