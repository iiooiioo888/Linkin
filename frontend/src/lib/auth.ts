/**
 * 前端閘門狀態：會話票存放於本機，請求時帶 X-Linkin-Gate。
 * 帳密校驗只在後端進行，此檔不含任何身分明文。
 */
const TOKEN_KEY = 'evoloop.runtime';
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

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

export async function loginGate(username: string, password: string): Promise<{ ok: true; user: string } | { ok: false; error: string }> {
  let resp: Response;
  try {
    resp = await fetch(apiUrl('/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ username, password }),
    });
  } catch {
    return { ok: false, error: '後端未連線，無法驗證' };
  }
  if (!resp.ok) {
    let detail = '帳號或密碼不正確';
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    return { ok: false, error: detail };
  }
  const data = (await resp.json()) as { token?: string; user?: string };
  const token = data.token ?? '';
  const user = data.user || username.trim();
  if (!token) return { ok: false, error: '登入回應異常' };
  writeRecord({ t: token, u: user, exp: Date.now() + 12 * 3600 * 1000 });
  return { ok: true, user };
}

export async function verifyGate(): Promise<boolean> {
  const token = getGateToken();
  if (!token) return false;
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
  try {
    await fetch(apiUrl('/auth/logout'), {
      method: 'POST',
      credentials: 'include',
      headers: token ? { 'X-Linkin-Gate': token } : {},
    });
  } catch {
    /* ignore */
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
        !isHub
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
