/**
 * Firecrawl 分頁：單頁抓取（含圖片）與網頁搜尋。
 */
import { useMemo, type Dispatch, type SetStateAction } from 'react';
import type { FirecrawlScrapeResult } from '../../api/client';
import { extractMarkdownImages } from '../../lib/visualCards';
import MediaGallery from '../media/MediaGallery';
import ErrorState from '../ui/ErrorState';

export function FirecrawlTab({
  fcUrl,
  setFcUrl,
  fcQuery,
  setFcQuery,
  fcScrape,
  fcSearchMarkdown,
  fcLoading,
  fcError,
  runFirecrawlScrape,
  runFirecrawlSearch,
}: {
  fcUrl: string;
  setFcUrl: Dispatch<SetStateAction<string>>;
  fcQuery: string;
  setFcQuery: Dispatch<SetStateAction<string>>;
  fcScrape: FirecrawlScrapeResult | null;
  fcSearchMarkdown: string;
  fcLoading: boolean;
  fcError: string | null;
  runFirecrawlScrape: () => Promise<void>;
  runFirecrawlSearch: () => Promise<void>;
}) {
  const scrapeImages = useMemo(
    () => (fcScrape ? extractMarkdownImages(fcScrape.markdown, fcScrape.url) : []),
    [fcScrape],
  );

  return (
          <div className="mx-auto max-w-3xl space-y-4">
            <section className="apple-card apple-card--pad space-y-3">
              <p className="apple-title">單頁抓取 · Scrape</p>
              <p className="text-[11px] text-[var(--console-sub)]">
                有 FIRECRAWL_API_KEY 時走官方 API；否則輕量 httpx 抓取。
              </p>
              <div className="flex flex-wrap gap-2">
                <input
                  value={fcUrl}
                  onChange={(e) => setFcUrl(e.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-[var(--console-card)] px-3 py-2 text-[12px] text-[var(--console-ink)]"
                />
                <button
                  type="button"
                  disabled={fcLoading}
                  onClick={() => void runFirecrawlScrape()}
                  className="rounded-full bg-[var(--console-amber)] px-4 py-2 text-[12px] font-bold text-white disabled:opacity-50"
                >
                  Scrape
                </button>
              </div>
              {fcScrape && (
                <div className="rounded-xl border border-white/[0.06] bg-black/20 p-3">
                  <p className="text-[12px] font-semibold text-[var(--console-ink)]">{fcScrape.title}</p>
                  <p className="mt-1 text-[10px] text-[var(--console-sub)]">
                    {fcScrape.url} · {fcScrape.source}
                  </p>
                  {fcScrape.hint && (
                    <p className="mt-2 text-[10px] text-[var(--console-amber)]">{fcScrape.hint}</p>
                  )}
                  {scrapeImages.length > 0 && (
                    <div className="mt-3">
                      <MediaGallery
                        items={scrapeImages.map((img) => ({
                          src: img.src,
                          caption: img.caption,
                          alt: img.caption,
                          tags: 'scrape',
                        }))}
                        layout="masonry"
                      />
                    </div>
                  )}
                  <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-[11px] text-[var(--console-sub)]">
                    {fcScrape.markdown}
                  </pre>
                </div>
              )}
            </section>
            <section className="apple-card apple-card--pad space-y-3">
              <p className="apple-title">網頁搜尋 · Search</p>
              <div className="flex flex-wrap gap-2">
                <input
                  value={fcQuery}
                  onChange={(e) => setFcQuery(e.target.value)}
                  className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-[var(--console-card)] px-3 py-2 text-[12px] text-[var(--console-ink)]"
                />
                <button
                  type="button"
                  disabled={fcLoading}
                  onClick={() => void runFirecrawlSearch()}
                  className="rounded-full border border-white/10 px-4 py-2 text-[12px] font-bold text-[var(--console-ink)] disabled:opacity-50"
                >
                  Search
                </button>
              </div>
              {fcSearchMarkdown && (
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-black/20 p-3 text-[11px] text-[var(--console-sub)]">
                  {fcSearchMarkdown}
                </pre>
              )}
            </section>
            {fcError && <ErrorState kind="generic" compact message={fcError} />}
          </div>
  );
}
