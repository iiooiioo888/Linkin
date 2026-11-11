/**
 * 整合面板單一整合卡：狀態、文件連結、連線設定與動作區。
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { saveIntegrationSettings } from '../../api/integrations';
import type { IntegrationStatus } from '../../api/integrations';
import { metaOf } from '../../lib/integrationsUi';
import { btnCls, btnPrimaryCls, cardCls, healthLabel, healthTone, inputCls } from './helpers';

export function IntegrationCard({
  item,
  busy,
  focused,
  forceOpen,
  onToggle,
  onSaved,
  onError,
  children,
}: {
  item: IntegrationStatus;
  busy: boolean;
  focused?: boolean;
  forceOpen?: boolean;
  onToggle: (enabled: boolean) => void;
  onSaved: (message: string) => void;
  onError: (message: string) => void;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(Boolean(forceOpen));
  const [baseUrl, setBaseUrl] = useState(item.base_url || '');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLElement>(null);
  const meta = metaOf(item.name);

  useEffect(() => {
    setBaseUrl(item.base_url || '');
  }, [item.base_url]);

  useEffect(() => {
    if (forceOpen) setOpen(true);
  }, [forceOpen]);

  useEffect(() => {
    if (focused && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focused]);

  return (
    <article
      ref={ref}
      id={`integ-${item.name}`}
      className={`${cardCls}${focused ? ' integ-panel-focus' : ''}`}
      style={{ ['--integ-accent' as string]: meta?.accent || 'var(--console-blue)' }}
    >
      <div className="flex items-start gap-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/[0.08] text-[16px]"
          style={{
            color: meta?.accent,
            background: `color-mix(in srgb, ${meta?.accent || 'var(--console-blue)'} 14%, transparent)`,
          }}
          aria-hidden
        >
          {meta?.glyph || '⧉'}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">{item.display_name || item.name}</h3>
            <span className={`text-[10px] ${healthTone(item)}`}>{healthLabel(item)}</span>
            {item.docs_url ? (
              <a
                href={item.docs_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full border border-white/[0.08] px-2 py-0.5 text-[10px] text-[var(--console-sub)] hover:console-status-blue"
              >
                文件 ↗
              </a>
            ) : null}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--console-sub)]">{item.summary}</p>
          <p className="mt-1 font-mono text-[10px] text-[var(--console-faint)]">{item.base_url}</p>
        </div>
        <label className="flex shrink-0 cursor-pointer items-center gap-2 text-[11px] text-[var(--console-sub)]">
          <span>{item.enabled ? '啟用' : '關閉'}</span>
          <input
            type="checkbox"
            className="accent-[var(--console-accent)]"
            checked={item.enabled}
            disabled={busy}
            onChange={(e) => onToggle(e.target.checked)}
          />
        </label>
      </div>
      <form
        className="mt-3 grid gap-2 border-t border-white/[0.06] pt-3 sm:grid-cols-[1fr_1fr_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          setSaving(true);
          void saveIntegrationSettings(item.name, {
            base_url: baseUrl.trim(),
            api_key: apiKey.trim() || undefined,
          })
            .then(() => {
              setApiKey('');
              onSaved(`${item.display_name || item.name} 連線已儲存到此帳號`);
            })
            .catch((err: Error) => onError(err.message))
            .finally(() => setSaving(false));
        }}
      >
        <input
          className={inputCls}
          value={baseUrl}
          onChange={(event) => setBaseUrl(event.target.value)}
          placeholder="服務網址"
          aria-label={`${item.display_name || item.name} 網址`}
        />
        <input
          className={inputCls}
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder={item.has_api_key ? `金鑰已設定 ${item.api_key_masked || ''}（留空不改）` : 'API 金鑰（選填）'}
          aria-label={`${item.display_name || item.name} 金鑰`}
          autoComplete="off"
        />
        <button type="submit" className={btnPrimaryCls} disabled={saving || busy}>
          {saving ? '儲存中…' : '儲存連線'}
        </button>
      </form>
      {item.enabled ? (
        <div className="mt-3 border-t border-white/[0.06] pt-3">
          <button type="button" className={btnCls} onClick={() => setOpen((v) => !v)}>
            {open ? '收合動作' : '展開動作'}
          </button>
          {open ? <div className="mt-3 space-y-3">{children}</div> : null}
        </div>
      ) : (
        <p className="mt-2 text-[10px] text-[var(--console-faint)]">啟用後才可發出網路請求（顯式動作）。</p>
      )}
    </article>
  );
}
