/**
 * 四入口殼。頁面來自 routes/mounts；缺檔時顯示「尚未接上」，不另開產品面。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { logoutGate } from '../lib/auth';
import {
  hashForSurface,
  surfaceFromHash,
  type SurfaceId,
} from './catalog';
import { loadSurfaces } from './loadMounts';

function UnmountedSurface() {
  return (
    <div
      className="flex flex-1 items-center justify-center px-6"
      data-testid="surface-unmounted"
    >
      <p className="text-[15px] font-medium text-[var(--console-ink)]">尚未接上</p>
    </div>
  );
}

export default function Shell() {
  const { t } = useTranslation();
  const surfaces = useMemo(() => loadSurfaces(), []);
  const [active, setActive] = useState<SurfaceId>(() =>
    typeof window === 'undefined' ? 'chat' : surfaceFromHash(window.location.hash),
  );

  const show = useCallback((id: SurfaceId, mode: 'push' | 'replace') => {
    const next = hashForSurface(id);
    if (window.location.hash !== next) {
      if (mode === 'push') window.location.hash = next;
      else window.history.replaceState(null, '', next);
    }
    setActive(id);
  }, []);

  useEffect(() => {
    const sync = () => {
      const id = surfaceFromHash(window.location.hash);
      setActive(id);
      const next = hashForSurface(id);
      if (window.location.hash !== next) {
        window.history.replaceState(null, '', next);
      }
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);

  const entry = surfaces.find((item) => item.id === active) ?? surfaces[0];
  const Page = entry?.ready ? entry.Page : null;

  return (
    <div className="app-shell flex h-dvh flex-col apple-canvas text-[var(--console-ink)]">
      <header className="app-topbar flex shrink-0 items-center gap-3 border-b apple-chrome px-4">
        <span className="brand-mark shrink-0 text-[14px] text-[var(--console-ink)] sm:text-[15px]">
          <span className="brand-mark__name">靈境</span>
          <span className="brand-mark__dot">·</span>
          <span className="hidden min-[400px]:inline font-medium tracking-tight">Linkin</span>
        </span>
        <nav
          className="flex min-w-0 flex-1 gap-1 overflow-x-auto"
          aria-label="主要功能"
          data-testid="surface-nav"
        >
          {surfaces.map((item) => {
            const current = item.id === active;
            return (
              <button
                key={item.id}
                type="button"
                data-surface={item.id}
                aria-current={current ? 'page' : undefined}
                onClick={() => show(item.id, 'push')}
                className={
                  current
                    ? 'shrink-0 rounded-[10px] bg-[var(--console-accent)] px-3 py-1.5 text-[13px] font-medium text-[var(--console-accent-ink)]'
                    : 'shrink-0 rounded-[10px] px-3 py-1.5 text-[13px] text-[var(--console-ink)] hover:bg-[color-mix(in_srgb,var(--console-ink)_6%,transparent)]'
                }
              >
                {item.label}
              </button>
            );
          })}
        </nav>
        <button
          type="button"
          onClick={() => void logoutGate()}
          className="apple-icon-btn shrink-0 text-[10px] font-semibold"
          aria-label={t('gate.signOut')}
        >
          {t('gate.signOut')}
        </button>
      </header>
      <main className="flex min-h-0 flex-1 flex-col">
        {Page ? <Page /> : <UnmountedSurface />}
      </main>
    </div>
  );
}
