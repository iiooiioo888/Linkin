/**
 * neiki-gallery React 包裝：砌體／網格／馬賽克／燈箱／畫中畫。
 * 關閉 hashNavigation，避免與 Linkin 的 #/ 路由衝突。
 */
import { useEffect, useId, useMemo, useRef } from 'react';
import { getNeikiGallery, type NeikiGalleryInstance } from '../../vendor/neiki-gallery';

export type GalleryItem = {
  src: string;
  thumb?: string;
  caption?: string;
  alt?: string;
  tags?: string;
  size?: 'small' | 'large';
};

export type GalleryLayout = 'masonry' | 'grid' | 'mosaic' | 'filmstrip';

export default function MediaGallery({
  items,
  layout = 'masonry',
  filter = false,
  className = '',
  empty = '尚無影像',
  onOpen,
}: {
  items: GalleryItem[];
  layout?: GalleryLayout;
  filter?: boolean;
  className?: string;
  empty?: string;
  onOpen?: (item: GalleryItem, index: number) => void;
}) {
  const uid = useId().replace(/:/g, '');
  const root = useRef<HTMLDivElement>(null);
  const gallery = useRef<NeikiGalleryInstance | null>(null);
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;
  const payload = useMemo(() => JSON.stringify({ items, layout, filter }), [items, layout, filter]);

  useEffect(() => {
    const el = root.current;
    if (!el || items.length === 0) return;
    let instance: NeikiGalleryInstance | null = null;
    try {
      const Ctor = getNeikiGallery();
      instance = new Ctor(el, {
        layout,
        theme: 'dark',
        loop: true,
        thumbnails: true,
        zoom: true,
        fullscreen: true,
        transition: 'fade',
        counter: true,
        stagger: true,
        pip: true,
        filter,
        share: false,
        hashNavigation: false,
        slideshow: { interval: 4500, pauseOnHover: true, kenburns: false },
        video: true,
        shortcutsHelp: true,
        infoPanel: true,
        virtualScroll: items.length > 24,
      });
      instance.on?.('open', (...args: unknown[]) => {
        const raw = args[0];
        const index =
          typeof raw === 'number'
            ? raw
            : typeof raw === 'object' && raw != null && 'index' in raw
              ? Number((raw as { index: number }).index)
              : 0;
        const item = items[index];
        if (item) onOpenRef.current?.(item, index);
      });
      gallery.current = instance;
    } catch (err) {
      console.warn('[neiki-gallery]', err);
    }
    return () => {
      instance?.destroy?.();
      gallery.current = null;
    };
  }, [payload, items, layout, filter]);

  if (items.length === 0) {
    return <p className={`py-8 text-center text-xs text-[#636366] ${className}`}>{empty}</p>;
  }

  return (
    <div
      ref={root}
      id={`neiki-${uid}`}
      className={`neiki-gallery media-gallery media-gallery--${layout} ${className}`}
      data-theme="dark"
      data-layout={layout}
      data-pip="true"
    >
      {items.map((item, index) => (
        <a
          key={`${item.src}-${index}`}
          href={item.src}
          data-caption={item.caption || item.alt || ''}
          data-tags={item.tags || undefined}
          data-size={item.size}
        >
          <img src={item.thumb || item.src} alt={item.alt || item.caption || ''} loading="lazy" />
        </a>
      ))}
    </div>
  );
}

export function VisualThumb({
  src,
  alt,
  className = 'h-10 w-10',
}: {
  src: string;
  alt: string;
  className?: string;
}) {
  return <img src={src} alt={alt} className={`shrink-0 rounded-lg object-cover ${className}`} />;
}
