/**
 * ServerMapPanel — 內嵌 Dynmap／BlueMap／Squaremap 網頁地圖。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchMinecraftPluginSettings,
  probeMinecraftPlugin,
  type MinecraftPluginSettings,
} from '../../api/linkin';
import { navPathForTab } from '../../lib/monitorTabs';

export default function ServerMapPanel() {
  const [settings, setSettings] = useState<MinecraftPluginSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const frameRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSettings(await fetchMinecraftPluginSettings());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const mapUrl = settings?.map_url?.trim() || '';
  const activePlugin = settings?.active_map_plugin;
  const lastProbe = activePlugin ? settings?.plugins?.[activePlugin]?.last_probe : undefined;

  const onProbe = async () => {
    if (!activePlugin) {
      setError('請先在插件中心設定並選擇預設地圖插件');
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await probeMinecraftPlugin(activePlugin);
      setMessage(result.probe.ok ? '地圖 URL 可連線' : `探測失敗：${result.probe.error || '無法連線'}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const toggleFullscreen = async () => {
    const el = frameRef.current;
    if (!fullscreen && el?.requestFullscreen) {
      await el.requestFullscreen();
      setFullscreen(true);
      return;
    }
    if (fullscreen && document.fullscreenElement) {
      await document.exitFullscreen();
    }
    setFullscreen(false);
  };

  useEffect(() => {
    const onFs = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-[#c9a961]">伺服器地圖</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            內嵌已設定的網頁地圖。於「{navPathForTab('plugin-hub')}」填寫 URL 並探測。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
          >
            重新整理
          </button>
          <button
            type="button"
            disabled={!mapUrl}
            onClick={() => setReloadKey((k) => k + 1)}
            className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8] disabled:opacity-40"
          >
            重載地圖
          </button>
          <button
            type="button"
            disabled={!mapUrl || busy}
            onClick={() => void onProbe()}
            className="rounded-xl border border-[#c9a961]/40 bg-[#c9a961]/10 px-2 py-1 text-[11px] text-[#c9a961] disabled:opacity-40"
          >
            {busy ? '探測中…' : '健康檢查'}
          </button>
          {mapUrl && (
            <>
              <button
                type="button"
                onClick={() => void toggleFullscreen()}
                className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
              >
                {fullscreen ? '退出全螢幕' : '全螢幕'}
              </button>
              <a
                href={mapUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]"
              >
                新分頁開啟
              </a>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      )}
      {message && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {message}
        </div>
      )}

      {lastProbe?.checked_at && (
        <p className="mb-2 text-[10px] text-[#636366]">
          上次健康檢查：{lastProbe.checked_at}
          {lastProbe.status_code != null ? ` · HTTP ${lastProbe.status_code}` : ''}
          {lastProbe.ok ? ' · 可連線' : ' · 無法連線'}
        </p>
      )}

      {!mapUrl ? (
        <div className="flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed border-[#c9a961]/30 bg-[#1C1C1E] p-8 text-center">
          <p className="mb-2 text-sm font-medium text-[#c9a961]">尚未設定地圖 URL</p>
          <ol className="max-w-md space-y-2 text-left text-[11px] text-[#8a8f98]">
            <li>1. 在伺服器安裝 Dynmap、BlueMap 或 Squaremap 並確認網頁地圖可公開存取。</li>
            <li>2. 打開「{navPathForTab('plugin-hub')}」，啟用地圖插件並填入公開 URL。</li>
            <li>3. 點「探測 URL」確認連線，再「設為預設地圖」。</li>
            <li>4. 回到本頁即可內嵌檢視；若 iframe 被阻擋，請用反向代理或新分頁開啟。</li>
          </ol>
        </div>
      ) : (
        <div
          ref={frameRef}
          className={`relative min-h-0 flex-1 overflow-hidden rounded-xl border border-[#c9a961]/20 bg-black ${fullscreen ? 'fixed inset-0 z-50 rounded-none border-0' : ''}`}
        >
          <iframe
            key={reloadKey}
            title="Minecraft 伺服器地圖"
            src={mapUrl}
            className="h-full w-full border-0 bg-[#0a0a0a]"
            allow="fullscreen"
            referrerPolicy="no-referrer"
          />
        </div>
      )}
    </div>
  );
}
