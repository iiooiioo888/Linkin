import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ModulePageProps } from '../types';
import ControlPanel from './ControlPanel';
import GalleryPanel from './GalleryPanel';
import MonitorPanel from './MonitorPanel';
import RelatedReposFooter from './RelatedReposFooter';

export type MediaVaultTab = 'control' | 'monitor' | 'gallery';

const TABS: ReadonlyArray<{ key: MediaVaultTab; label: string }> = [
  { key: 'control', label: '控制' },
  { key: 'monitor', label: '監控' },
  { key: 'gallery', label: '圖庫' },
];

function tabFromPage(page: string | undefined): MediaVaultTab {
  if (page === 'gallery' || page === 'monitor' || page === 'control') return page;
  return 'control';
}

function hashForTab(tab: MediaVaultTab): string {
  return tab === 'control' ? '#/modules/media-vault' : `#/modules/media-vault/${tab}`;
}

/** 採集媒體庫統一入口：控制／監控／圖庫（面板 API 獨立，僅共享導航狀態）。 */
export default function MediaVaultHub({ moduleId, page }: ModulePageProps) {
  const initialTab = useMemo(() => tabFromPage(page), [page]);
  const [active, setActive] = useState<MediaVaultTab>(initialTab);
  const [batchFocus, setBatchFocus] = useState('');

  useEffect(() => {
    setActive(tabFromPage(page));
  }, [page]);

  const selectTab = useCallback((tab: MediaVaultTab) => {
    setActive(tab);
    const next = hashForTab(tab);
    if (window.location.hash !== next) {
      window.location.hash = next;
    }
  }, []);

  const openMonitor = useCallback(
    (batchId: string) => {
      setBatchFocus(batchId);
      selectTab('monitor');
    },
    [selectTab],
  );

  const openGallery = useCallback(
    (batchId: string) => {
      setBatchFocus(batchId);
      selectTab('gallery');
    },
    [selectTab],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col" data-testid="media-vault-hub">
      <header className="shrink-0 border-b border-[var(--console-line)] px-4 pt-3">
        <h1 className="text-[15px] font-semibold text-[var(--console-ink)]">採集 · 媒體庫</h1>
        <p className="pb-2 text-[11px] text-[var(--console-sub)]">Media Vault — 控制、監控與圖庫一體化</p>
        <nav className="flex gap-1" role="tablist" aria-label="媒體庫">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={active === key}
              data-testid={`media-vault-tab-${key}`}
              className={`rounded-t px-3 py-1.5 text-[12px] ${
                active === key
                  ? 'bg-[var(--console-sidebar)] font-medium text-[var(--console-ink)]'
                  : 'text-[var(--console-sub)] hover:text-[var(--console-ink)]'
              }`}
              onClick={() => selectTab(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {active === 'control' ? (
          <ControlPanel onOpenGallery={openGallery} onOpenMonitor={openMonitor} />
        ) : active === 'gallery' ? (
          <GalleryPanel
            moduleId={moduleId}
            page="gallery"
            initialBatchId={batchFocus}
            onOpenMonitor={openMonitor}
          />
        ) : (
          <MonitorPanel
            moduleId={moduleId}
            page="monitor"
            focusBatchId={batchFocus}
            onOpenGalleryBatch={openGallery}
          />
        )}
      </div>

      <RelatedReposFooter />
    </div>
  );
}
