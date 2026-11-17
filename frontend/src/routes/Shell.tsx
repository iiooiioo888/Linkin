/**
 * 四入口殼。高頻入口在左欄：對話、歷史。壓縮兩項收在底部「進階」。
 * 登出在欄底。金絲只標示正在使用的那一項。
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

const PRIMARY: SurfaceId[] = ['chat', 'history'];
const ADVANCED: SurfaceId[] = ['context-compression', 'prompt-compression'];

function UnmountedSurface({ title }: { title: string }) {
  return (
    <section className="surface-stage">
      <h1 className="surface-stage__title">{title}</h1>
      <p className="surface-stage__note" data-testid="surface-unmounted">
        尚未接上
      </p>
    </section>
  );
}

function NavIcon({ id }: { id: SurfaceId | 'more' | 'out' }) {
  const d =
    id === 'chat'
      ? 'M5 6.5h14v8.5H8.5L5 18.5V6.5z'
      : id === 'history'
        ? 'M12 7v5l3 2M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z'
        : id === 'context-compression'
          ? 'M5 8h14M5 12h10M5 16h12'
          : id === 'prompt-compression'
            ? 'M7 7h10v10H7zM4 4h4M16 4h4M4 16v4M16 20h4'
            : id === 'more'
              ? 'M6 8h12M6 12h12M6 16h8'
              : 'M10 7V5H5v14h5v-2M10 12h9M16 9l3 3-3 3';
  return (
    <svg className="surface-shell__ico" viewBox="0 0 24 24" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export default function Shell() {
  const { t } = useTranslation();
  const surfaces = useMemo(() => loadSurfaces(), []);
  const [active, setActive] = useState<SurfaceId>(() =>
    typeof window === 'undefined' ? 'chat' : surfaceFromHash(window.location.hash),
  );
  const [advancedOpen, setAdvancedOpen] = useState(() =>
    ADVANCED.includes(typeof window === 'undefined' ? 'chat' : surfaceFromHash(window.location.hash)),
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
      if (ADVANCED.includes(id)) setAdvancedOpen(true);
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
  const byId = (id: SurfaceId) => surfaces.find((item) => item.id === id);

  return (
    <div className="surface-shell">
      <nav className="surface-shell__nav" aria-label="主要功能" data-testid="surface-nav" data-zone="left">
        <span className="brand-mark surface-shell__brand text-[14px] text-[var(--console-ink)]">
          <span className="brand-mark__name">靈境</span>
          <span className="brand-mark__dot">·</span>
          <span className="font-medium tracking-tight">Linkin</span>
        </span>
        <div className="surface-shell__primary">
          {PRIMARY.map((id) => {
            const item = byId(id);
            if (!item) return null;
            return (
              <button
                key={id}
                type="button"
                data-surface={id}
                aria-current={id === active ? 'page' : undefined}
                onClick={() => show(id, 'push')}
                className="surface-shell__link"
              >
                <NavIcon id={id} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
        <div className="surface-shell__foot">
          <button
            type="button"
            className="surface-shell__link surface-shell__more"
            aria-expanded={advancedOpen}
            aria-controls="surface-advanced"
            onClick={() => setAdvancedOpen((open) => !open)}
          >
            <NavIcon id="more" />
            <span>進階</span>
          </button>
          <div id="surface-advanced" className="surface-shell__advanced" hidden={!advancedOpen}>
            {ADVANCED.map((id) => {
              const item = byId(id);
              if (!item) return null;
              return (
                <button
                  key={id}
                  type="button"
                  data-surface={id}
                  aria-current={id === active ? 'page' : undefined}
                  onClick={() => show(id, 'push')}
                  className="surface-shell__link surface-shell__link--sub"
                >
                  <NavIcon id={id} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
          <button
            type="button"
            onClick={() => void logoutGate()}
            className="surface-shell__link surface-shell__signout"
            aria-label={t('gate.signOut')}
          >
            <NavIcon id="out" />
            <span>{t('gate.signOut')}</span>
          </button>
        </div>
      </nav>
      <main className="surface-shell__stage">
        {Page ? <Page /> : <UnmountedSurface title={entry?.label ?? ''} />}
      </main>
    </div>
  );
}
