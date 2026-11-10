/**
 * 前端閘門狀態。會話權杖只留在後端設的 HttpOnly Cookie（REACT-AUTH-001）。
 * 這裡只記顯示用的帳號，不記權杖。靜態站不再在瀏覽器裡核對登入秘密。
 */
const USER_KEY = 'evoloop.gateUser';
const LEGACY_TOKEN_KEY = 'evoloop.runtime';
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

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

const AUTH_EVENT = 'linkin-auth-changed';

function clearLegacyToken() {
  try {
    localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

clearLegacyToken();

function readUser(): string | null {
  try {
    const user = sessionStorage.getItem(USER_KEY);
    return user || null;
  } catch {
    return null;
  }
}

function writeUser(user: string) {
  clearLegacyToken();
  try {
    sessionStorage.setItem(USER_KEY, user);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function getGateUser(): string | null {
  return readUser();
}

export function hasGate(): boolean {
  return Boolean(readUser());
}

export function clearGate() {
  clearLegacyToken();
  try {
    sessionStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function subscribeGate(listener: () => void): () => void {
  window.addEventListener(AUTH_EVENT, listener);
  return () => window.removeEventListener(AUTH_EVENT, listener);
}

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

type RemoteLogin =
  | { kind: 'ok'; user: string }
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
  if (!resp.ok || !looksLikeJson(resp)) return { kind: 'offline' };
  try {
    const data = (await resp.json()) as { ok?: boolean; user?: string };
    if (!data.ok && !data.user) return { kind: 'offline' };
    return { kind: 'ok', user: data.user || username.trim() };
  } catch {
    return { kind: 'offline' };
  }
}

export async function loginGate(username: string, password: string): Promise<{ ok: true; user: string } | { ok: false; error: string }> {
  if (isStaticHost()) {
    return { ok: false, error: '此部署沒有登入服務' };
  }
  const remote = await tryRemoteLogin(username, password);
  if (remote.kind === 'ok') {
    writeUser(remote.user);
    return { ok: true, user: remote.user };
  }
  if (remote.kind === 'denied') return { ok: false, error: remote.error };
  return { ok: false, error: '登入服務無法連線' };
}

export async function verifyGate(): Promise<boolean> {
  clearLegacyToken();
  if (isStaticHost()) {
    clearGate();
    return false;
  }
  try {
    const resp = await fetch(apiUrl('/auth/me'), { credentials: 'include' });
    if (resp.status === 401) {
      clearGate();
      return false;
    }
    if (!resp.ok) return hasGate();
    const data = (await resp.json()) as { user?: string };
    if (data.user) writeUser(data.user);
    return true;
  } catch {
    return hasGate();
  }
}

export async function logoutGate(): Promise<void> {
  if (!isStaticHost()) {
    try {
      await fetch(apiUrl('/auth/logout'), {
        method: 'POST',
        credentials: 'include',
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
  return { ...init, credentials: init?.credentials ?? 'include' };
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
      if (resp.status === 401 && shouldAttach(url) && !url.includes('/auth/login') && !isHub) {
        clearGate();
      }
      return resp;
    });
  };
}

/** WebSocket 走同站 Cookie，不再把權杖放進網址（FASTAPI-AUTH-002）。 */
export function appendGateQuery(url: string): string {
  return url;
}
