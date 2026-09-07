/**
 * neiki-gallery v3.2.0（MIT）— 本地 vendor，避免執行期 CDN。
 * 原始專案：https://github.com/neikiri/neiki-gallery
 */
import './neiki-gallery.min.js';

export type NeikiGalleryInstance = {
  destroy?: () => void;
  refresh?: () => void;
  on?: (event: string, cb: (...args: unknown[]) => void) => void;
};

export type NeikiCompareInstance = {
  destroy?: () => void;
};

type NeikiGalleryCtor = (new (
  el: string | HTMLElement,
  options?: Record<string, unknown>,
) => NeikiGalleryInstance) & {
  compare?: (
    el: string | HTMLElement,
    options?: Record<string, unknown>,
  ) => NeikiCompareInstance;
};

export function getNeikiGallery(): NeikiGalleryCtor {
  const ctor = (globalThis as unknown as { NeikiGallery?: NeikiGalleryCtor }).NeikiGallery;
  if (!ctor) {
    throw new Error('NeikiGallery 未載入');
  }
  return ctor;
}

export function compareImages(
  el: string | HTMLElement,
  options: {
    before: string;
    after: string;
    labelBefore?: string;
    labelAfter?: string;
    startPosition?: number;
  },
): NeikiCompareInstance {
  const compare = getNeikiGallery().compare;
  if (!compare) {
    throw new Error('NeikiGallery.compare 不可用');
  }
  return compare(el, options);
}
