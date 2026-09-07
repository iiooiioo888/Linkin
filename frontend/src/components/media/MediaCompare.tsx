/**
 * neiki-gallery 前後對比滑桿（Picture comparison）。
 */
import { useEffect, useRef } from 'react';
import { compareImages } from '../../vendor/neiki-gallery';

export default function MediaCompare({
  before,
  after,
  labelBefore = '之前',
  labelAfter = '之後',
  className = '',
}: {
  before: string;
  after: string;
  labelBefore?: string;
  labelAfter?: string;
  className?: string;
}) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || !before || !after) return;
    let slider: { destroy?: () => void } | null = null;
    try {
      slider = compareImages(el, {
        before,
        after,
        labelBefore,
        labelAfter,
        startPosition: 50,
      });
    } catch (err) {
      console.warn('[neiki-gallery.compare]', err);
    }
    return () => {
      slider?.destroy?.();
    };
  }, [before, after, labelBefore, labelAfter]);

  return (
    <div
      ref={root}
      className={`media-compare ${className}`}
      data-before={before}
      data-after={after}
    />
  );
}
