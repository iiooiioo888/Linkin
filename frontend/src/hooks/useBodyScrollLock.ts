import { useEffect } from 'react';

/** 鎖定 body 滾動（行動端抽屜／遮罩開啟時）。 */
export function useBodyScrollLock(locked: boolean): void {
  useEffect(() => {
    if (!locked) return;
    const prev = document.body.style.overflow;
    document.body.classList.add('scroll-lock');
    return () => {
      document.body.classList.remove('scroll-lock');
      document.body.style.overflow = prev;
    };
  }, [locked]);
}
