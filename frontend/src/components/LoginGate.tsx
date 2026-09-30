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
      </form>
    </div>
  );
}
