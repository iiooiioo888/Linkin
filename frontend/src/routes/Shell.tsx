/**
 * 控制台殼。頂列、左欄兩組入口、主欄、右欄。
 * 導覽只放四個入口；登出在頂列。窄螢幕改為底部四鍵。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { getGateUser, logoutGate } from '../lib/auth';
import { PATH_LABEL } from '../lib/executionPath';
import {
  hashForSurface,
  surfaceFromHash,
  type SurfaceId,
} from './catalog';
import { ConsoleDeck, ConsoleRailPanels, useConsoleFacts } from './ConsoleChrome';
import { InfraRailNotes, InfraSections } from './InfraPanels';
import { loadSurfaces } from './loadMounts';

const GROUPS: { label: string; en: string; ids: SurfaceId[] }[] = [
  { label: '運行', en: 'RUNTIME', ids: ['chat', 'history'] },
  { label: '壓縮', en: 'COMPRESS', ids: ['context-compression', 'prompt-compression'] },
];

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
  const facts = useConsoleFacts();
  const clock = useClock();
  const [query, setQuery] = useState('');
  const [more, setMore] = useState(false);
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

  return (
    <div className="surface-shell">
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
        <span className="brand-sub">Runtime · 統一管線 · 反思閉環</span>
        <div className="chip-row">
          <span className="chip amber">{entry?.label}</span>
          <span className="chip or">Docker Compose</span>
          <span className="chip vi">阿里雲 · 唯讀</span>
          <span className="chip">{facts.path ? PATH_LABEL[facts.path.path] : '路徑未選'}</span>
          <span className="chip">{facts.sessions ? `${facts.sessions} 會話` : '尚無會話'}</span>
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
          <span className={`live${facts.llm === 'yes' ? ' is-on' : ''}`}>
            <span className="dot" aria-hidden />
            {facts.llm === 'yes' ? '模型已設定' : facts.llm === 'no' ? '模型未設定' : '待命'}
          </span>
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
            <div className="rail-label">
              <span>{group.label}</span>
              <span>{group.en}</span>
            </div>
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
        {entry ? <ConsoleDeck surface={entry.id} label={entry.label} /> : null}
        {Page ? <Page /> : <UnmountedSurface title={entry?.label ?? ''} />}
        <InfraSections />
      </main>
      <aside className="rail-right" data-zone="right">
        {active === 'chat' ? <div id="console-rail" className="console-rail" /> : null}
        <InfraRailNotes />
        <ConsoleRailPanels />
      </aside>
      <nav className="tabs" aria-label="窄螢幕">
        <button type="button" className="nav-item" aria-current={active === 'chat' ? 'page' : undefined} onClick={() => show('chat', 'push')}>
          <span className="nm">對話</span>
        </button>
        <button type="button" className="nav-item" onClick={() => { show('chat', 'push'); window.setTimeout(() => document.getElementById('c-task')?.scrollIntoView({ block: 'start' }), 40); }}>
          <span className="nm">任務</span>
        </button>
        <button type="button" className="nav-item" onClick={() => document.getElementById('c-docker')?.scrollIntoView({ block: 'start' })}>
          <span className="nm">Docker</span>
        </button>
        <button type="button" className="nav-item" onClick={() => document.getElementById('c-aliyun')?.scrollIntoView({ block: 'start' })}>
          <span className="nm">雲資源</span>
        </button>
        <button type="button" className="nav-item" aria-expanded={more} onClick={() => setMore((open) => !open)}>
          <span className="nm">更多</span>
        </button>
        {more ? (
          <div className="tabs-more">
            {surfaces.filter((item) => item.id !== 'chat').map((item) => (
              <button key={item.id} type="button" className="nav-item" onClick={() => { setMore(false); show(item.id, 'push'); }}>
                <span className="nm">{item.label}</span>
              </button>
            ))}
          </div>
        ) : null}
      </nav>
    </div>
  );
}
