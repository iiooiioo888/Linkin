/**
 * 全屏登入閘門：通過後才渲染主應用。
 * 視覺：OPC v3 gold/dark card + 分層金字塔標誌 + 角色網路背景。
 */
import { useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { hasGate, loginGate, subscribeGate, verifyGate } from '../lib/auth';
import OpcNetworkBackground from './login/OpcNetworkBackground';
import OpcPyramidLogo from './login/OpcPyramidLogo';
import './login/login.css';

const REMEMBER_KEY = 'linkin.rememberDevice';
const REMEMBERED_USER_KEY = 'linkin.rememberedUser';
const APP_VERSION = '0.0.0';

interface LoginGateProps {
  children: ReactNode;
}

function readRememberDevice(): boolean {
  try {
    return localStorage.getItem(REMEMBER_KEY) === '1';
  } catch {
    return false;
  }
}

function readRememberedUser(): string {
  try {
    return localStorage.getItem(REMEMBERED_USER_KEY) ?? '';
  } catch {
    return '';
  }
}

export default function LoginGate({ children }: LoginGateProps) {
  const { t } = useTranslation();
  const [ready, setReady] = useState(false);
  const [ok, setOk] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(readRememberDevice);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [latency, setLatency] = useState(12);

  useEffect(() => {
    if (readRememberDevice()) {
      const saved = readRememberedUser();
      if (saved) setUsername(saved);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!hasGate()) {
        if (!cancelled) {
          setOk(false);
          setReady(true);
        }
        return;
      }
      const valid = await verifyGate();
      if (!cancelled) {
        setOk(valid);
        setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    return subscribeGate(() => setOk(hasGate()));
  }, []);

  useEffect(() => {
    const tick = () => setLatency(8 + Math.floor(Math.random() * 18));
    tick();
    const id = window.setInterval(tick, 4200);
    return () => window.clearInterval(id);
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await loginGate(username, password);
      if (!result.ok) {
        setError(result.error);
        setPassword('');
        return;
      }
      try {
        localStorage.setItem(REMEMBER_KEY, remember ? '1' : '0');
        if (remember) localStorage.setItem(REMEMBERED_USER_KEY, username.trim());
        else localStorage.removeItem(REMEMBERED_USER_KEY);
      } catch {
        /* ignore */
      }
      setOk(true);
    } catch {
      setError(t('gate.failed'));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  if (!ready) {
    return <div className="login-page" />;
  }
  if (ok) {
    return <>{children}</>;
  }

  return (
    <div className="login-page">
      <OpcNetworkBackground />
      <form className="login-card" onSubmit={onSubmit} autoComplete="on">
        <div className="login-status">
          <div className="login-status__left">
            <span className="login-status__dot" aria-hidden="true" />
            <span className="login-status__core">{t('gate.statusCore')}</span>
            <span className="login-status__online">{t('gate.statusOnline')}</span>
          </div>
          <span>AP-01 · {latency}ms</span>
        </div>

        <div className="login-brand">
          <OpcPyramidLogo className="login-logo" />
          <h1 className="login-title">
            {t('gate.titlePrefix')}
            <span className="login-title__accent">Linkin</span>
          </h1>
          <p className="login-sub">{t('gate.subtitle')}</p>
        </div>

        <div className="login-form">
          <label className="login-label" htmlFor="gate-user">
            {t('gate.account')}
          </label>
          <input
            id="gate-user"
            className="login-field"
            name="username"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />

          <label className="login-label" htmlFor="gate-secret">
            {t('gate.secret')}
          </label>
          <input
            id="gate-secret"
            className="login-field"
            name="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          <div className="login-row">
            <label className="login-remember">
              <input
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              {t('gate.rememberDevice')}
            </label>
            <button type="button" className="login-forgot" tabIndex={-1}>
              {t('gate.forgotPassword')}
            </button>
          </div>

          {error ? <p className="login-error">{error}</p> : null}

          <button
            className="login-submit"
            type="submit"
            disabled={busy || !username.trim() || !password}
          >
            {busy ? t('gate.checking') : t('gate.enter')}
          </button>
        </div>

        <footer className="login-footer">
          <span className="login-footer__secure">{t('gate.secure')}</span>
          <span className="login-footer__sep">·</span>
          <span>v{APP_VERSION}</span>
          <span className="login-footer__sep">·</span>
          <span>TLS 1.3</span>
        </footer>
      </form>
    </div>
  );
}
