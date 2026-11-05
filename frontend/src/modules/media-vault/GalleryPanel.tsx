import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchMediaVaultDetail,
  fetchMediaVaultImages,
  mediaVaultFileUrl,
  type MediaVaultPost,
} from '../../lib/mediaVaultApi';

const PLATFORMS = ['xhs', 'dy', 'bili', 'wb', 'zhihu', 'ks', 'tieba'];
const COMPLIANCE = ['public', 'licensed', 'internal', 'unknown', 'restricted', 'prohibited'];
const RISKS = ['green', 'yellow', 'red'];

type Props = {
  moduleId: string;
  page: string;
  initialBatchId?: string;
  onOpenMonitor?: (batchId: string) => void;
};

export default function GalleryPanel({ initialBatchId, onOpenMonitor }: Props) {
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [batchId, setBatchId] = useState(initialBatchId ?? '');
  const [compliance, setCompliance] = useState('');
  const [mediaType, setMediaType] = useState('');
  const [risk, setRisk] = useState('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<MediaVaultPost[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<MediaVaultPost | null>(null);
  const [lightbox, setLightbox] = useState<MediaVaultPost | null>(null);

  const filters = useMemo(
    () => ({
      platform: platforms.length ? platforms : undefined,
      batch_id: batchId || undefined,
      compliance_basis: compliance || undefined,
      media_type: mediaType || undefined,
      risk_level: risk || undefined,
      q: q || undefined,
      page_size: 48,
    }),
    [platforms, batchId, compliance, mediaType, risk, q],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchMediaVaultImages(filters);
      setItems(data.items);
      setTotal(data.total);
    } catch {
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (initialBatchId) setBatchId(initialBatchId);
  }, [initialBatchId]);

  const openDetail = async (post: MediaVaultPost) => {
    try {
      const detail = await fetchMediaVaultDetail(post.id);
      setSelected(detail);
      setLightbox(detail);
    } catch {
      setSelected(post);
      setLightbox(post);
    }
  };

  const togglePlatform = (p: string) => {
    setPlatforms((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden" data-testid="media-vault-gallery">
      <header className="sticky top-0 z-10 flex flex-wrap items-end gap-3 border-b border-[var(--console-line)] bg-[var(--console-canvas)] px-4 py-3 backdrop-blur-sm">
        <div>
          <p className="text-[12px] font-medium text-[var(--console-ink)]">图库</p>
          <p className="text-[11px] text-[var(--console-sub)]">共 {loading ? '…' : total} 筆</p>
        </div>
        <div className="flex flex-1 flex-wrap gap-2 text-[11px]">
          <input
            className="min-w-[120px] rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1"
            placeholder="批次 ID"
            value={batchId}
            onChange={(e) => setBatchId(e.target.value)}
          />
          <input
            className="min-w-[140px] flex-1 rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1"
            placeholder="作者 / URL"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <select
            className="rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1"
            value={compliance}
            onChange={(e) => setCompliance(e.target.value)}
          >
            <option value="">合規</option>
            {COMPLIANCE.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1"
            value={mediaType}
            onChange={(e) => setMediaType(e.target.value)}
          >
            <option value="">類型</option>
            <option value="image">image</option>
            <option value="text">text</option>
          </select>
          <select
            className="rounded border border-[var(--console-line)] bg-[var(--console-bg)] px-2 py-1"
            value={risk}
            onChange={(e) => setRisk(e.target.value)}
          >
            <option value="">風險</option>
            {RISKS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
      </header>

      <div className="flex flex-wrap gap-1 px-4 pt-3">
        {PLATFORMS.map((p) => (
          <button
            key={p}
            type="button"
            className={`rounded px-2 py-0.5 text-[10px] uppercase tracking-wide ${
              platforms.includes(p)
                ? 'bg-[var(--console-accent)] text-white'
                : 'border border-[var(--console-line)] text-[var(--console-sub)]'
            }`}
            onClick={() => togglePlatform(p)}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-2">
      {loading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" data-testid="media-vault-gallery-skeleton">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className="aspect-square animate-pulse rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)]"
            />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 py-16 text-center" data-testid="media-vault-gallery-empty">
          <p className="text-[13px] font-medium text-[var(--console-ink)]">尚无媒资</p>
          <p className="max-w-sm text-[11px] text-[var(--console-sub)]">
            在「控制」页启动 MediaCrawler 任务，完成后点击「入庫」，或在此调整筛选条件。
          </p>
        </div>
      ) : (
        <div className="grid auto-rows-max grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5" data-testid="media-vault-gallery-grid">
          {items.map((post) => (
            <button
              key={post.id}
              type="button"
              className="group relative overflow-hidden rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)] text-left shadow-sm transition hover:border-[var(--console-accent)]"
              onClick={() => void openDetail(post)}
            >
              <div
                className="absolute left-0 top-0 z-10 h-1 w-full"
                style={{
                  background:
                    post.risk_level === 'green'
                      ? '#22c55e'
                      : post.risk_level === 'red'
                        ? '#ef4444'
                        : '#eab308',
                }}
              />
              {post.thumb_url ? (
                <img
                  src={mediaVaultFileUrl(post.thumb_url)}
                  alt=""
                  className="aspect-square w-full object-cover"
                  loading="lazy"
                />
              ) : (
                <div className="flex aspect-square items-center justify-center text-[11px] text-[var(--console-sub)]">
                  {post.media_type}
                </div>
              )}
              <div className="space-y-0.5 p-2">
                <span className="inline-block rounded bg-black/40 px-1 text-[9px] uppercase text-white">
                  {post.platform}
                </span>
                <p className="truncate text-[11px] font-medium text-[var(--console-ink)]">
                  {post.author || '—'}
                </p>
                <p className="text-[10px] text-[var(--console-sub)]">{post.ingested_at?.slice(0, 16)}</p>
              </div>
            </button>
          ))}
        </div>
      )}
      </div>

      {lightbox ? (
        <div
          className="fixed inset-0 z-50 flex bg-black/80 p-4"
          role="dialog"
          aria-modal
          onClick={() => setLightbox(null)}
        >
          <div
            className="ml-auto flex h-full max-w-md flex-col gap-3 overflow-y-auto rounded-lg border border-[var(--console-line)] bg-[var(--console-sidebar)] p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <button type="button" className="self-end text-[12px] text-[var(--console-sub)]" onClick={() => setLightbox(null)}>
              關閉
            </button>
            {selected?.assets?.find((a) => a.kind === 'thumb_800' || a.kind === 'original') ? (
              <img
                src={mediaVaultFileUrl(
                  selected.assets.find((a) => a.kind === 'thumb_800')?.url ||
                    selected.assets.find((a) => a.kind === 'original')?.url ||
                    '',
                )}
                alt=""
                className="max-h-[50vh] w-full rounded object-contain"
              />
            ) : null}
            <dl className="space-y-1 text-[11px] text-[var(--console-ink)]">
              <div>
                <dt className="text-[var(--console-sub)]">來源</dt>
                <dd className="break-all">{selected?.source_url || '—'}</dd>
              </div>
              <div>
                <dt className="text-[var(--console-sub)]">crawl_method</dt>
                <dd>{selected?.crawl_method}</dd>
              </div>
              <div>
                <dt className="text-[var(--console-sub)]">compliance_basis</dt>
                <dd>{selected?.compliance_basis}</dd>
              </div>
              <div>
                <dt className="text-[var(--console-sub)]">dedup_hash</dt>
                <dd className="break-all font-mono text-[10px]">{selected?.dedup_hash}</dd>
              </div>
            </dl>
            {selected?.batch_id && onOpenMonitor ? (
              <button
                type="button"
                className="rounded bg-[var(--console-accent)] px-3 py-1.5 text-[11px] text-white"
                onClick={() => onOpenMonitor(selected.batch_id)}
              >
                查看該批次監控
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
