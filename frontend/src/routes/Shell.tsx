/**
 * 四入口與品名同一列。窄螢幕改成兩行，名稱不截斷。
 * 登出不在導覽裡，導覽只放四個入口。
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
    <div className="surface-shell">
      <header className="surface-shell__bar" data-zone="top">
        <span className="brand-mark surface-shell__brand">
          <span>靈境</span>
          <span className="brand-mark__dot">·</span>
          <span>Linkin</span>
        </span>
        <nav className="surface-shell__nav" aria-label="主要功能" data-testid="surface-nav" data-zone="left">
          {surfaces.map((item) => (
            <button
              key={item.id}
              type="button"
              data-surface={item.id}
              aria-current={item.id === active ? 'page' : undefined}
              onClick={() => show(item.id, 'push')}
              className="surface-shell__link"
            >
              {item.label}
            </button>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => void logoutGate()}
          className="surface-shell__signout"
          aria-label={t('gate.signOut')}
        >
          {t('gate.signOut')}
        </button>
      </header>
      <main className="surface-shell__stage">
        {Page ? <Page /> : <UnmountedSurface title={entry?.label ?? ''} />}
      </main>
    </div>
  );
}
