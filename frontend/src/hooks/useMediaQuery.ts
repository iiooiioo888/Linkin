import { useEffect, useState } from 'react';
import {
  DESKTOP_SHELL_MEDIA,
  MOBILE_SHELL_MEDIA,
  type ShellMode,
} from '../lib/mobileShell';

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
  return useMediaQuery(DESKTOP_SHELL_MEDIA, true);
}

/** <768px 窄螢幕（與 Tailwind `md` 互補）。 */
export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_SHELL_MEDIA, false);
}

/**
 * 行動 Lite Shell：<768px 時啟用精簡呈現策略。
 * 能力/API 不裁切，僅控制面密度與三欄 chrome。
 */
export function useIsMobileLiteShell(): boolean {
  return useIsMobile();
}

/** 同步 shell 模式（供非 React 或 CSS 資料屬性使用）。 */
export function useShellMode(): ShellMode {
  const isMobile = useIsMobile();
  return isMobile ? 'lite' : 'full';
}
