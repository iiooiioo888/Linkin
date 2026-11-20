/**
 * 控制台殼。頂列、左欄兩組入口、主欄、右欄。
 * 導覽只放四個入口；登出在頂列。窄螢幕改為底部四鍵。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getGateUser, logoutGate } from '../lib/auth';
import {
  hashForSurface,
  surfaceFromHash,
  type SurfaceId,
} from './catalog';
import { loadSurfaces } from './loadMounts';

const GROUPS: { label: string; ids: SurfaceId[] }[] = [
  { label: '運行', ids: ['chat', 'history'] },
  { label: '壓縮', ids: ['context-compression', 'prompt-compression'] },
];

const RAIL_NOTE: Partial<Record<SurfaceId, string>> = {
  'context-compression': '規則截斷與關鍵句抽取，不經模型。空白上限會用各函式的預設值。',
  'prompt-compression': '保留頭尾並截掉中間。不經模型，也不改寫用詞。空白上限用後端預設。',
};

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

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return now.toLocaleTimeString('zh-TW', { hour12: false });
}

export default function Shell() {
  const { t } = useTranslation();
  const surfaces = useMemo(() => loadSurfaces(), []);
  const clock = useClock();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState<SurfaceId>(() =>
    typeof window === 'undefined' ? 'chat' : surfaceFromHash(window.location.hash),
  );
  const user = typeof window === 'undefined' ? null : getGateUser();

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
  const needle = query.trim();
  const visible = (label: string) => !needle || label.includes(needle);

  const links = (className: string) =>
    surfaces.map((item) => (
      <button
        key={`${className}-${item.id}`}
        type="button"
        data-surface={item.id}
        hidden={className === 'rail' ? !visible(item.label) : undefined}
        aria-current={item.id === active ? 'page' : undefined}
        onClick={() => show(item.id, 'push')}
        className="nav-item"
      >
        <span className="nm">{item.label}</span>
      </button>
    ));

  return (
    <div className={`surface-shell${active === 'history' ? ' is-history' : ''}`}>
      <header className="topbar" data-zone="top">
        <div className="brand">
          <svg className="brand-glyph" viewBox="0 0 30 30" aria-hidden>
            <rect x="1.5" y="1.5" width="27" height="27" rx="4" fill="none" stroke="currentColor" strokeWidth="1.4" />
            <path d="M8 21 L15 8 L22 21" fill="none" stroke="currentColor" strokeWidth="1.4" />
          </svg>
          <span className="brand-name">
            靈境·<em>Linkin</em>
          </span>
        </div>
        <span className="brand-sub">統一管線</span>
        <div className="chip-row">
          <span className="chip amber">{entry?.label}</span>
        </div>
        <label className="searchbox">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="尋找入口"
            aria-label="尋找入口"
          />
        </label>
        <div className="top-right">
          <time className="clock" dateTime={new Date().toISOString()}>
            {clock}
          </time>
          <button type="button" className="topbar-signout" onClick={() => void logoutGate()} aria-label={t('gate.signOut')}>
            {user ? <span className="topbar-user">{user}</span> : null}
            {t('gate.signOut')}
          </button>
        </div>
      </header>
      <nav className="rail" aria-label="主要功能" data-testid="surface-nav" data-zone="left">
        {GROUPS.map((group) => (
          <div key={group.label} className="rail-group">
            <div className="rail-label">{group.label}</div>
            {surfaces
              .filter((item) => group.ids.includes(item.id))
              .map((item) => (
                <button
                  key={item.id}
                  type="button"
                  data-surface={item.id}
                  hidden={!visible(item.label)}
                  aria-current={item.id === active ? 'page' : undefined}
                  onClick={() => show(item.id, 'push')}
                  className="nav-item"
                >
                  <span className="nm">{item.label}</span>
                </button>
              ))}
          </div>
        ))}
      </nav>
      <main className="stage">
        {Page ? <Page /> : <UnmountedSurface title={entry?.label ?? ''} />}
      </main>
      {active === 'history' ? null : (
        <aside className="rail-right" data-zone="right">
          {active === 'chat' ? (
            <div id="console-rail" className="console-rail" />
          ) : (
            <section className="panel">
              <div className="panel-head">
                <h2 className="panel-title">{entry?.label}</h2>
              </div>
              <div className="panel-body">{entry ? RAIL_NOTE[entry.id] : ''}</div>
            </section>
          )}
        </aside>
      )}
      <nav className="tabs" aria-label="主要功能">
        {links('tabs')}
      </nav>
    </div>
  );
}
