/**
 * 可視化插件分頁：dsh-plugin 目錄與啟用切換。
 */

import { useCallback, useEffect, useState } from 'react';
import { fetchPlugins, togglePlugin, type PluginCatalogEntry } from '../../api/plugins';
import { openChatContextDetail, openContextModal } from '../../lib/contextUi';
import { jumpToContextMonitor } from '../../lib/rahoUi';
import { consoleLayout } from '../ui/ConsoleLayout';
import { ErrorBar, OkBar } from './shared';
import { btnCls, btnPrimaryCls, cardCls } from './styles';

export function VizPluginsSection() {
  const [items, setItems] = useState<PluginCatalogEntry[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await fetchPlugins();
      setItems(data.catalog || []);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onToggle = async (pluginId: string, enabled: boolean) => {
    setBusyId(pluginId);
    setError(null);
    setMessage(null);
    try {
      const out = await togglePlugin(pluginId, enabled);
      if (!out.ok) throw new Error('切換失敗');
      setMessage(`${pluginId} 已${enabled ? '啟用' : '停用'}（顯式動作）`);
      if (out.catalog) setItems(out.catalog);
      else await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <ErrorBar message={error} />
      <OkBar message={message} />
      <p className="mb-3 text-[12px] leading-relaxed text-[var(--console-sub)]">
        dsh-plugin 可視化適配。預設關閉；啟用後解鎖 Context 面板／瀏覽器／
        <code className="text-[11px] text-[var(--console-sub)]">/context</code> 命令表面。靈感來自{' '}
        <a
          href="https://github.com/bowenliang123/dsh-context"
          target="_blank"
          rel="noopener noreferrer"
          className="console-status-blue hover:underline"
        >
          dsh-context
        </a>
        ；本機適配、不遠端拉取 npm。
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        {items.map((p) => (
          <article key={p.plugin_id} className={cardCls} data-testid={`viz-plugin-${p.plugin_id}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">{p.display_name || p.plugin_id}</h3>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--console-sub)]">{p.summary}</p>
                <p className="mt-1 font-mono text-[10px] text-[var(--console-faint)]">
                  {p.repo} · pin {p.pin_version || p.default_pin || '—'} · {p.source_tag}
                </p>
                {p.commands?.length ? (
                  <p className="mt-1 text-[10px] text-[var(--console-sub)]">命令：{p.commands.join(' · ')}</p>
                ) : null}
              </div>
              <label className="flex shrink-0 cursor-pointer items-center gap-2 text-[11px] text-[var(--console-sub)]">
                <span>{p.enabled ? '啟用' : '關閉'}</span>
                <input
                  type="checkbox"
                  className="accent-[var(--console-accent)]"
                  checked={Boolean(p.enabled)}
                  disabled={busyId === p.plugin_id}
                  onChange={(e) => void onToggle(p.plugin_id, e.target.checked)}
                />
              </label>
            </div>
            {p.plugin_id === 'dsh-context' ? (
              <div className="mt-3 flex flex-wrap gap-2 border-t border-white/[0.06] pt-3">
                <button type="button" className={btnPrimaryCls} onClick={() => openChatContextDetail()}>
                  對話 Context 詳細區
                </button>
                <button type="button" className={btnCls} onClick={() => openContextModal(null)}>
                  /context peek
                </button>
                <button type="button" className={btnCls} onClick={() => jumpToContextMonitor()}>
                  資產鏡像
                </button>
                {p.docs_url ? (
                  <a
                    href={p.docs_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`${btnCls} inline-flex items-center`}
                  >
                    上游文件 ↗
                  </a>
                ) : null}
              </div>
            ) : null}
          </article>
        ))}
        {items.length === 0 ? (
          <p className={`col-span-full ${consoleLayout.emptySm} text-[12px] text-[var(--console-faint)]`}>尚無可視化插件目錄</p>
        ) : null}
      </div>
    </div>
  );
}
