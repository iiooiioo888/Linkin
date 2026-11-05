import { useCallback, useState } from 'react';
import GalleryPanel from './GalleryPanel';
import MonitorPanel from './MonitorPanel';
import type { ModulePageProps } from '../types';

/** 宿主內切換展示／監控；各面板 API 獨立，僅共享 URL 狀態。 */
export default function MediaVaultShell({ moduleId, page }: ModulePageProps) {
  const [active, setActive] = useState<'gallery' | 'monitor'>(page === 'monitor' ? 'monitor' : 'gallery');
  const [batchFocus, setBatchFocus] = useState('');

  const openMonitor = useCallback((batchId: string) => {
    setBatchFocus(batchId);
    setActive('monitor');
  }, []);

  const openGallery = useCallback((batchId: string) => {
    setBatchFocus(batchId);
    setActive('gallery');
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav className="flex gap-1 border-b border-[var(--console-line)] px-4 pt-2">
        {(
          [
            ['gallery', '展示'],
            ['monitor', '監控'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`rounded-t px-3 py-1.5 text-[12px] ${
              active === key
                ? 'bg-[var(--console-sidebar)] font-medium text-[var(--console-ink)]'
                : 'text-[var(--console-sub)]'
            }`}
            onClick={() => setActive(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      {active === 'gallery' ? (
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
  );
}
