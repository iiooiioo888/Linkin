/**
 * 前端閘門狀態：會話票存放於本機，請求時帶 X-Linkin-Gate。
 * 有後端時走 /auth/login；GitHub Pages 等靜態站改以本機摘要核對。
 * 此檔不含任何身分明文。
 */
import { matchLocalGate } from './gateDigest';

const TOKEN_KEY = 'evoloop.runtime';
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';
const LOCAL_PREFIX = 'lg1.';

function hasRemoteApi(): boolean {
  const raw = import.meta.env.VITE_API_URL;
  return Boolean(raw && String(raw).trim());
}

function isStaticHost(): boolean {
  if (typeof window !== 'undefined' && /\.github\.io$/i.test(window.location.hostname)) {
    return true;
  }
  if (hasRemoteApi()) return false;
  return import.meta.env.VITE_GITHUB_PAGES === 'true';
}

type GateRecord = { t: string; u: string; exp: number };

const AUTH_EVENT = 'linkin-auth-changed';

function readRecord(): GateRecord | null {
  try {
    const raw = localStorage.getItem(TOKEN_KEY);
    if (!raw) return null;
    const rec = JSON.parse(raw) as GateRecord;
    if (!rec?.t || !rec?.u) return null;
    if (rec.exp && rec.exp < Date.now()) {
      localStorage.removeItem(TOKEN_KEY);
      return null;
    }
    return rec;
  } catch {
    return null;
  }
}

function writeRecord(rec: GateRecord) {
  localStorage.setItem(TOKEN_KEY, JSON.stringify(rec));
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function getGateToken(): string | null {
  return readRecord()?.t ?? null;
}

export function getGateUser(): string | null {
  return readRecord()?.u ?? null;
}

export function hasGate(): boolean {
  return Boolean(getGateToken());
}

export function clearGate() {
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function subscribeGate(listener: () => void): () => void {
  window.addEventListener(AUTH_EVENT, listener);
  return () => window.removeEventListener(AUTH_EVENT, listener);
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

function isLocalToken(token: string | null): boolean {
  return Boolean(token?.startsWith(LOCAL_PREFIX));
}

function issueLocalSession(user: string) {
  const nid =
    typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().replace(/-/g, '')
      : `${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  writeRecord({ t: `${LOCAL_PREFIX}${nid}`, u: user, exp: Date.now() + 12 * 3600 * 1000 });
}

type RemoteLogin =
  | { kind: 'ok'; token: string; user: string }
  | { kind: 'denied'; error: string }
  | { kind: 'offline' };

function looksLikeJson(resp: Response): boolean {
  return (resp.headers.get('content-type') || '').includes('application/json');
}

async function tryRemoteLogin(username: string, password: string): Promise<RemoteLogin> {
  let resp: Response;
  try {
    resp = await fetch(apiUrl('/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
      signal: AbortSignal.timeout(6000),
    });
  } catch {
    return { kind: 'offline' };
  }
  if (resp.status === 401 || resp.status === 429) {
    if (!looksLikeJson(resp)) return { kind: 'offline' };
    let detail = '帳號或密碼不正確';
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      return { kind: 'offline' };
    }
    return { kind: 'denied', error: detail };
  }
  if (!resp.ok) return { kind: 'offline' };
  if (!looksLikeJson(resp)) return { kind: 'offline' };
  try {
    const data = (await resp.json()) as { token?: string; user?: string };
    const token = data.token ?? '';
    if (!token) return { kind: 'offline' };
    return { kind: 'ok', token, user: data.user || username.trim() };
  } catch {
    return { kind: 'offline' };
  }
}

async function unlockLocal(username: string, password: string): Promise<{ ok: true; user: string } | { ok: false; error: string }> {
  const user = username.trim();
  let matched = false;
  try {
    matched = await matchLocalGate(user, password);
  } catch {
    return { ok: false, error: '本機核對失敗' };
  }
  if (!matched) return { ok: false, error: '帳號或密碼不正確' };
  issueLocalSession(user);
  return { ok: true, user };
}

export async function loginGate(username: string, password: string): Promise<{ ok: true; user: string } | { ok: false; error: string }> {
  // GitHub Pages 沒有後端：必須先走本機摘要，否則 /api/auth/login 的 401 HTML
  // 會被當成「密碼錯誤」。有後端時本機通過同樣放行（與預設摘要對相同）。
  const local = await unlockLocal(username, password);
  if (local.ok) return local;
  if (isStaticHost()) return local;

  const remote = await tryRemoteLogin(username, password);
  if (remote.kind === 'ok') {
    writeRecord({ t: remote.token, u: remote.user, exp: Date.now() + 12 * 3600 * 1000 });
    return { ok: true, user: remote.user };
  }
  if (remote.kind === 'denied') return { ok: false, error: remote.error };
  return local;
}

export async function verifyGate(): Promise<boolean> {
  const token = getGateToken();
  if (!token) return false;
  if (isLocalToken(token) || isStaticHost()) return true;
  try {
    const resp = await fetch(apiUrl('/auth/me'), {
      credentials: 'include',
      headers: { 'X-Linkin-Gate': token },
    });
    if (resp.status === 401) {
      clearGate();
      return false;
    }
    if (!resp.ok) return true;
    const data = (await resp.json()) as { user?: string };
    if (data.user) {
      writeRecord({ t: token, u: data.user, exp: Date.now() + 12 * 3600 * 1000 });
    }
    return true;
  } catch {
    return true;
  }
}

export async function logoutGate(): Promise<void> {
  const token = getGateToken();
  if (token && !isLocalToken(token) && !isStaticHost()) {
    try {
      await fetch(apiUrl('/auth/logout'), {
        method: 'POST',
        credentials: 'include',
        headers: { 'X-Linkin-Gate': token },
      });
    } catch {
      /* ignore */
    }
  }
  clearGate();
}

function shouldAttach(url: string): boolean {
  if (url.startsWith('/api') || url.includes('/api/')) return true;
  const base = API_BASE;
  if (base.startsWith('http') && url.startsWith(base)) return true;
  return false;
}

export function attachGateHeaders(init?: RequestInit): RequestInit {
  const token = getGateToken();
  if (!token) return init ?? {};
  const headers = new Headers(init?.headers);
  if (!headers.has('X-Linkin-Gate')) headers.set('X-Linkin-Gate', token);
  return { ...init, credentials: init?.credentials ?? 'include', headers };
}

export function installAuthFetch() {
  const native = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const next = shouldAttach(url) ? attachGateHeaders(init) : init;
    return native(input, next).then((resp) => {
      const isHub = url.includes('/api/v1') || url.includes('/v1/');
      if (
        resp.status === 401 &&
        shouldAttach(url) &&
        !url.includes('/auth/login') &&
        !isHub &&
        !isLocalToken(getGateToken())
      ) {
        clearGate();
      }
      return resp;
    });
  };
}

export function appendGateQuery(url: string): string {
  const token = getGateToken();
  if (!token) return url;
  const join = url.includes('?') ? '&' : '?';
  return `${url}${join}gate=${encodeURIComponent(token)}`;
}
