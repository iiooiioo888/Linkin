/**
 * 全屏登入閘門：通過後才渲染主應用。
 */
import { useEffect, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { hasGate, loginGate, subscribeGate, verifyGate } from '../lib/auth';

interface LoginGateProps {
  children: ReactNode;
}

export default function LoginGate({ children }: LoginGateProps) {
  const { t } = useTranslation();
  const [ready, setReady] = useState(false);
  const [ok, setOk] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      setOk(true);
    } catch {
      setError(t('gate.failed'));
      setPassword('');
    } finally {
      setBusy(false);
    }
  };

  if (!ready) {
    return <div className="gate-page" />;
  }
  if (ok) {
    return <>{children}</>;
  }

  return (
    <div className="gate-page">
      <form className="gate-card" onSubmit={onSubmit} autoComplete="on">
        <p className="gate-kicker">EvoLoop</p>
        <h1 className="gate-title">靈境·Linkin</h1>
        <p className="gate-sub">{t('gate.subtitle')}</p>

        <label className="gate-label" htmlFor="gate-user">
          {t('gate.account')}
        </label>
        <input
          id="gate-user"
          className="apple-field gate-field"
          name="username"
          autoComplete="username"
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />

        <label className="gate-label" htmlFor="gate-secret">
          {t('gate.secret')}
        </label>
        <input
          id="gate-secret"
          className="apple-field gate-field"
          name="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error ? <p className="gate-error">{error}</p> : null}

        <button className="gate-submit" type="submit" disabled={busy || !username.trim() || !password}>
          {busy ? t('gate.checking') : t('gate.enter')}
        </button>
      </form>
    </div>
  );
}
