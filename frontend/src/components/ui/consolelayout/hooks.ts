/**
 * 單頁區塊導航 hooks：IntersectionObserver scroll spy 與平滑滾動。
 */

import { useCallback, useEffect, useState, type RefObject } from 'react';

/** IntersectionObserver scroll spy for single-page section nav */
export function useSectionScrollSpy(
  sectionIds: string[],
  scrollRootRef: RefObject<HTMLElement | null>,
): string | undefined {
  const [active, setActive] = useState<string | undefined>(sectionIds[0]);

  useEffect(() => {
    const root = scrollRootRef.current;
    if (!root || sectionIds.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        const id = visible[0]?.target.id;
        if (id) setActive(id);
      },
      { root, rootMargin: '-12% 0px -55% 0px', threshold: [0, 0.15, 0.4, 0.65] },
    );

    for (const id of sectionIds) {
      const el = root.querySelector(`#${CSS.escape(id)}`);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sectionIds, scrollRootRef]);

  return active;
}

export function useScrollToSection(scrollRootRef: RefObject<HTMLElement | null>) {
  return useCallback(
    (id: string) => {
      const root = scrollRootRef.current;
      const el =
        root?.querySelector(`#${CSS.escape(id)}`) ??
        document.getElementById(id);
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
    [scrollRootRef],
  );
}
