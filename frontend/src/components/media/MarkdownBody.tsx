import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { extractMarkdownImages } from '../../lib/visualCards';
import MediaGallery from './MediaGallery';

export default function MarkdownBody({
  markdown,
  className = 'markdown-body',
}: {
  markdown: string;
  className?: string;
}) {
  const images = useMemo(() => extractMarkdownImages(markdown), [markdown]);
  const srcSet = useMemo(() => new Set(images.map((img) => img.src)), [images]);

  return (
    <div className={className}>
      <ReactMarkdown
        components={{
          img: ({ src, alt }) => {
            if (!src) return null;
            if (srcSet.has(src) || images.length > 0) return null;
            return (
              <a href={src} data-caption={alt || ''} className="inline-block max-w-full">
                <img src={src} alt={alt || ''} className="max-h-72 rounded-xl" />
              </a>
            );
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
      {images.length > 0 && (
        <div className="mt-3">
          <MediaGallery
            items={images.map((img) => ({ src: img.src, caption: img.caption, alt: img.caption }))}
            layout={images.length === 1 ? 'grid' : images.length > 6 ? 'masonry' : 'filmstrip'}
          />
        </div>
      )}
    </div>
  );
}
