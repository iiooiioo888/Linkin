/**
 * 統一模組目錄與業務客戶端。
 * 新模組只打 /modules/{id}/api/{path}，不要直連控制台或各模組內部前綴。
 */
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

export type ModuleRosterKind = 'agents' | 'tasks';

export type ModuleCatalogItem = {
  id: string;
  title: string;
  description: string;
  version?: string;
  kind?: string;
  icon?: string;
  default_page?: string;
  enabled?: boolean;
  api_prefix?: string;
  gateway_prefix?: string;
  capabilities?: Array<{
    id: string;
    title: string;
    description: string;
    api_prefix: string;
    routes: string[];
  }>;
  nav_groups?: Array<{
    id: string;
    label: string;
    items: Array<{
      key: string;
      icon: string;
      label: string;
      hint?: string;
      capability?: string;
      roster?: ModuleRosterKind;
    }>;
  }>;
  pages?: Array<{
    key: string;
    group: string;
    group_label?: string;
    icon: string;
    label: string;
    hint?: string;
    capability?: string | null;
    api_prefix: string;
    routes: string[];
    roster?: ModuleRosterKind | null;
  }>;
  page_aliases?: Record<string, string>;
};

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

/** 統一業務路徑：/modules/{id}/api/{route} */
export function moduleApiPath(moduleId: string, route: string): string {
  const rel = route.startsWith('/') ? route : `/${route}`;
  return `/modules/${encodeURIComponent(moduleId)}/api${rel}`;
}

export function moduleUrl(moduleId: string, route: string): string {
  return apiUrl(moduleApiPath(moduleId, route));
}

function httpError(status: number, data: unknown, text: string): string {
  if (status === 405) {
    return '後端不接受此操作（HTTP 405）。請重啟 python -m backend.main 後再試。';
  }
  const detail = (data as { detail?: unknown })?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    if ('message' in detail) return String((detail as { message: string }).message);
    if ('error_code' in detail) {
      const code = String((detail as { error_code: string }).error_code);
      return code === 'ERR_SNAPSHOT_UNRESOLVED'
        ? 'L0 快照已更新，請先重綁或丟棄草稿後再提交。'
        : `敘事工作區錯誤：${code}`;
    }
  }
  return text?.trim() ? text.trim().slice(0, 240) : `請求失敗（HTTP ${status}）`;
}

async function parseBody(resp: Response): Promise<unknown> {
  const text = await resp.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export async function moduleRequest<T>(moduleId: string, route: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type') && init?.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }
  const resp = await fetch(moduleUrl(moduleId, route), { ...init, headers });
  const data = await parseBody(resp);
  if (!resp.ok) throw new Error(httpError(resp.status, data, typeof data === 'string' ? data : ''));
  return data as T;
}

export async function moduleFormRequest<T>(moduleId: string, route: string, form: FormData): Promise<T> {
  const resp = await fetch(moduleUrl(moduleId, route), { method: 'POST', body: form });
  const data = await parseBody(resp);
  if (!resp.ok) throw new Error(httpError(resp.status, data, typeof data === 'string' ? data : ''));
  return data as T;
}

export type ModuleClient = {
  id: string;
  path: (route: string) => string;
  url: (route: string) => string;
  get: <T>(route: string) => Promise<T>;
  post: <T>(route: string, body?: unknown) => Promise<T>;
  put: <T>(route: string, body?: unknown) => Promise<T>;
  del: <T>(route: string) => Promise<T>;
  form: <T>(route: string, form: FormData) => Promise<T>;
};

/** 後續世界／整合模組共用：createModuleClient('foo').get('/bar') */
export function createModuleClient(moduleId: string): ModuleClient {
  return {
    id: moduleId,
    path: (route) => moduleApiPath(moduleId, route),
    url: (route) => moduleUrl(moduleId, route),
    get: (route) => moduleRequest(moduleId, route),
    post: (route, body) =>
      moduleRequest(moduleId, route, {
        method: 'POST',
        body: body === undefined ? '{}' : JSON.stringify(body),
      }),
    put: (route, body) =>
      moduleRequest(moduleId, route, {
        method: 'PUT',
        body: body === undefined ? '{}' : JSON.stringify(body),
      }),
    del: (route) => moduleRequest(moduleId, route, { method: 'DELETE' }),
    form: (route, form) => moduleFormRequest(moduleId, route, form),
  };
}

async function readJson<T>(path: string): Promise<T> {
  const resp = await fetch(apiUrl(path));
  if (!resp.ok) {
    throw new Error(`模組目錄失敗（HTTP ${resp.status}）`);
  }
  return (await resp.json()) as T;
}

export async function fetchModuleCatalog(): Promise<ModuleCatalogItem[]> {
  const data = await readJson<{ modules: ModuleCatalogItem[] }>('/modules');
  return Array.isArray(data.modules) ? data.modules : [];
}

export async function fetchModuleHealth(moduleId: string): Promise<Record<string, unknown>> {
  return readJson<Record<string, unknown>>(`/modules/${encodeURIComponent(moduleId)}/health`);
}

export async function fetchModule(moduleId: string): Promise<ModuleCatalogItem> {
  return readJson<ModuleCatalogItem>(`/modules/${encodeURIComponent(moduleId)}`);
}

export async function fetchModulePages(moduleId: string): Promise<{
  id: string;
  default_page: string;
  pages: NonNullable<ModuleCatalogItem['pages']>;
  count: number;
}> {
  return readJson(`/modules/${encodeURIComponent(moduleId)}/pages`);
}

export async function fetchModulePage(
  moduleId: string,
  page: string,
): Promise<{ id: string; page: NonNullable<ModuleCatalogItem['pages']>[number] }> {
  return readJson(`/modules/${encodeURIComponent(moduleId)}/pages/${encodeURIComponent(page)}`);
}

export async function fetchModuleCapabilities(moduleId: string): Promise<{
  id: string;
  api_prefix: string;
  gateway_prefix: string;
  capabilities: NonNullable<ModuleCatalogItem['capabilities']>;
  count: number;
}> {
  return readJson(`/modules/${encodeURIComponent(moduleId)}/capabilities`);
}
