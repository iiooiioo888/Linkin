/**
 * 插件目錄 API（含 dsh-context 可視化適配）。
 * 安裝／啟用皆為顯式動作；不遠端拉取 npm。
 */
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export type PluginKind = 'visualization' | string;

export interface PluginCatalogEntry {
  plugin_id: string;
  display_name: string;
  repo: string;
  source_tag: string;
  default_pin?: string;
  pin_version?: string;
  capability?: string;
  kind?: PluginKind;
  docs_url?: string;
  summary?: string;
  surfaces?: string[];
  commands?: string[];
  remote_fetch?: boolean;
  status: 'available' | 'installed' | 'enabled' | 'disabled' | 'degraded' | string;
  enabled?: boolean;
}

export interface PluginsPayload {
  catalog: PluginCatalogEntry[];
  installed: Array<Record<string, unknown>>;
  count: number;
}

async function readJson<T>(resp: Response, fallback: string): Promise<T> {
  if (!resp.ok) {
    let detail = fallback;
    try {
      const body = (await resp.json()) as { detail?: { error_code?: string } | string };
      if (typeof body.detail === 'object' && body.detail?.error_code) {
        detail = `${fallback}（${body.detail.error_code}）`;
      } else if (typeof body.detail === 'string') {
        detail = body.detail;
      }
    } catch {
      /* ignore */
    }
    throw new Error(`${detail}（HTTP ${resp.status}）`);
  }
  return resp.json() as Promise<T>;
}

export async function fetchPlugins(): Promise<PluginsPayload> {
  const resp = await fetch(apiUrl('/plugins'));
  return readJson(resp, '讀取插件目錄失敗');
}

export async function installPlugin(pluginId: string): Promise<{ ok: boolean; catalog?: PluginCatalogEntry[] }> {
  const resp = await fetch(apiUrl(`/plugins/${encodeURIComponent(pluginId)}/install`), {
    method: 'POST',
  });
  return readJson(resp, '安裝插件失敗');
}

export async function togglePlugin(
  pluginId: string,
  enabled: boolean,
): Promise<{ ok: boolean; enabled?: boolean; catalog?: PluginCatalogEntry[] }> {
  const resp = await fetch(apiUrl(`/plugins/${encodeURIComponent(pluginId)}/toggle`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  return readJson(resp, '切換插件失敗');
}
