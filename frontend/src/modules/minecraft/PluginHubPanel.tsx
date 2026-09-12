/**
 * PluginHubPanel — Minecraft 第三方插件目錄與連線設定。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  fetchMinecraftPluginCatalog,
  fetchMinecraftPluginSettings,
  probeMinecraftPlugin,
  saveMinecraftPluginSettings,
  type MinecraftPluginCatalogEntry,
  type MinecraftPluginSettings,
} from '../../api/linkin';
import { navPathForTab } from '../../lib/monitorTabs';

const STATUS_LABEL: Record<string, string> = {
  disabled: '未啟用',
  unconfigured: '未設定',
  configured: '已設定',
  reachable: '可連線',
  unreachable: '無法連線',
};

const STATUS_COLOR: Record<string, string> = {
  disabled: 'text-[#8a8f98]',
  unconfigured: 'text-amber-300',
  configured: 'text-[#c9a961]',
  reachable: 'text-emerald-300',
  unreachable: 'text-red-300',
};

export default function PluginHubPanel() {
  const [catalog, setCatalog] = useState<MinecraftPluginCatalogEntry[]>([]);
  const [settings, setSettings] = useState<MinecraftPluginSettings | null>(null);
  const [drafts, setDrafts] = useState<Record<string, { map_url: string; api_port: string; enabled: boolean }>>({});
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [cat, cfg] = await Promise.all([fetchMinecraftPluginCatalog(), fetchMinecraftPluginSettings()]);
      setCatalog(cat.plugins);
      setSettings(cfg);
      const next: Record<string, { map_url: string; api_port: string; enabled: boolean }> = {};
      for (const item of cat.plugins) {
        const stored = cfg.plugins[item.id] ?? {};
        next[item.id] = {
          map_url: stored.map_url ?? item.map_url ?? '',
          api_port: stored.api_port != null ? String(stored.api_port) : item.api_port != null ? String(item.api_port) : '',
          enabled: stored.enabled ?? item.enabled ?? false,
        };
      }
      setDrafts(next);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const savePlugin = async (pluginId: string) => {
    const draft = drafts[pluginId];
    if (!draft) return;
    setBusy(pluginId);
    setError(null);
    setMessage(null);
    try {
      const body = {
        plugins: {
          [pluginId]: {
            enabled: draft.enabled,
            map_url: draft.map_url.trim() || undefined,
            api_port: draft.api_port.trim() ? Number(draft.api_port) : null,
          },
        },
      };
      const saved = await saveMinecraftPluginSettings(body);
      setSettings(saved);
      setMessage(`${pluginId} 設定已保存`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const setActiveMap = async (pluginId: string) => {
    setBusy(`active-${pluginId}`);
    setError(null);
    try {
      const saved = await saveMinecraftPluginSettings({ active_map_plugin: pluginId });
      setSettings(saved);
      setMessage(`已將 ${pluginId} 設為預設地圖來源`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onProbe = async (pluginId: string) => {
    setBusy(`probe-${pluginId}`);
    setError(null);
    setMessage(null);
    try {
      const result = await probeMinecraftPlugin(pluginId);
      setMessage(
        result.probe.ok
          ? `${pluginId} 探測成功（HTTP ${result.probe.status_code ?? '—'}）`
          : `${pluginId} 探測失敗：${result.probe.error || result.connection_status}`,
      );
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const mapPlugins = catalog.filter((p) => p.category === 'map');
  const otherPlugins = catalog.filter((p) => p.category !== 'map');

  const renderCard = (item: MinecraftPluginCatalogEntry) => {
    const draft = drafts[item.id] ?? { map_url: '', api_port: '', enabled: false };
    const status = item.status ?? 'unconfigured';
    const isMap = item.category === 'map';
    return (
      <article
        key={item.id}
        className="rounded-xl border border-[#c9a961]/20 bg-[#1C1C1E] p-4 shadow-[inset_0_1px_0_rgba(201,169,97,0.06)]"
      >
        <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-[#f7f8f8]">{item.name}</h3>
            <p className="mt-0.5 text-[11px] text-[#8a8f98]">{item.purpose}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={`text-[10px] font-medium ${STATUS_COLOR[status] ?? 'text-[#8a8f98]'}`}>
              {STATUS_LABEL[status] ?? status}
            </span>
            {item.active_map && (
              <span className="rounded-md border border-[#c9a961]/40 bg-[#c9a961]/10 px-1.5 py-0.5 text-[10px] text-[#c9a961]">
                預設地圖
              </span>
            )}
            {item.embeddable && (
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">可嵌入</span>
            )}
          </div>
        </div>

        <p className="mb-2 text-[10px] text-[#636366]">
          平台：{item.platforms.join(' · ')} · 類別：{item.category}
        </p>
        <p className="mb-3 text-[11px] leading-relaxed text-[#AEAEB2]">{item.install_hint}</p>

        {item.config_fields.length > 0 && (
          <div className="mb-3 grid gap-2 lg:grid-cols-2">
            {item.config_fields.map((field) => (
              <label key={field.key} className="text-[10px] text-[#8a8f98]">
                {field.label}
                {field.required ? ' *' : ''}
                <input
                  value={field.key === 'map_url' ? draft.map_url : draft.api_port}
                  onChange={(e) =>
                    setDrafts((prev) => ({
                      ...prev,
                      [item.id]: {
                        ...draft,
                        [field.key === 'map_url' ? 'map_url' : 'api_port']: e.target.value,
                      },
                    }))
                  }
                  placeholder={field.example ?? ''}
                  className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[#f7f8f8]"
                />
              </label>
            ))}
          </div>
        )}

        <label className="mb-3 flex items-center gap-2 text-[11px] text-[#8a8f98]">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) =>
              setDrafts((prev) => ({
                ...prev,
                [item.id]: { ...draft, enabled: e.target.checked },
              }))
            }
          />
          啟用此插件整合
        </label>

        {item.last_probe?.checked_at && (
          <p className="mb-3 text-[10px] text-[#636366]">
            上次探測：{item.last_probe.checked_at}
            {item.last_probe.status_code != null ? ` · HTTP ${item.last_probe.status_code}` : ''}
            {item.last_probe.embeddable_hint ? ` · ${item.last_probe.embeddable_hint}` : ''}
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void savePlugin(item.id)}
            className="rounded-lg border border-[#c9a961]/40 bg-[#c9a961]/10 px-3 py-1.5 text-[12px] text-[#c9a961] disabled:opacity-40"
          >
            {busy === item.id ? '保存中…' : '保存設定'}
          </button>
          {isMap && draft.map_url.trim() && (
            <>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void onProbe(item.id)}
                className="rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-3 py-1.5 text-[12px] text-[#8a8f98] hover:text-[#f7f8f8] disabled:opacity-40"
              >
                {busy === `probe-${item.id}` ? '探測中…' : '探測 URL'}
              </button>
              <button
                type="button"
                disabled={busy !== null}
                onClick={() => void setActiveMap(item.id)}
                className="rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-3 py-1.5 text-[12px] text-[#8a8f98] hover:text-[#f7f8f8] disabled:opacity-40"
              >
                設為預設地圖
              </button>
            </>
          )}
        </div>
      </article>
    );
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-[#c9a961]">插件中心</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            設定 Dynmap／BlueMap／Squaremap 等地圖 URL，於「{navPathForTab('server-map')}」內嵌檢視。
            設定保存在後端，不會寫入前端。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
        >
          重新整理
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      )}
      {message && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {message}
        </div>
      )}

      {settings?.map_url && (
        <div className="mb-4 rounded-xl border border-[#c9a961]/30 bg-[#c9a961]/5 px-3 py-2 text-[11px] text-[#c9a961]">
          目前地圖 URL：{settings.map_url}
          {settings.active_map_plugin ? `（來源：${settings.active_map_plugin}）` : ''}
        </div>
      )}

      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">地圖插件</h3>
      <div className="mb-6 grid gap-3 lg:grid-cols-2">{mapPlugins.map(renderCard)}</div>

      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">NPC／任務／建築相關</h3>
      <div className="grid gap-3 lg:grid-cols-2">{otherPlugins.map(renderCard)}</div>

      <section className="mt-6 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3 text-[11px] text-[#8a8f98]">
        <h4 className="mb-1 font-semibold text-[#c9a961]">反向代理提示</h4>
        <p>
          若地圖站點阻擋 iframe（X-Frame-Options / CSP），可在 nginx 將地圖反代到 Linkin 同源路徑，例如{' '}
          <code className="text-[#AEAEB2]">/minecraft-map/</code> → 你的 Dynmap 埠，再在插件中心填寫{' '}
          <code className="text-[#AEAEB2]">https://linkin.example.com/minecraft-map/</code>。
        </p>
      </section>
    </div>
  );
}
