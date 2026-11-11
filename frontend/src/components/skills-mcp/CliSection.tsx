/**
 * CLI 相關區塊：CLI-Anything 目錄查詢與 CLI 運行時狀態列。
 */

import { useCallback, useEffect, useState } from 'react';
import {
  fetchCliHub,
  fetchCliRuntimes,
  type CliHubItem,
  type CliHubView,
  type CliRuntimeStatus,
} from '../../api/client';
import { btnCls, cardCls, inputCls } from './styles';

const CLI_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

function CliHubCatalog() {
  const [query, setQuery] = useState('');
  const [view, setView] = useState<CliHubView | null>(null);
  const [picked, setPicked] = useState<CliHubItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async (q: string) => {
    setBusy(true);
    setPicked(null);
    setCopied(false);
    try {
      const next = q.trim()
        ? await fetchCliHub({ action: 'search', query: q.trim() })
        : await fetchCliHub({ action: 'list', full: true });
      setView(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load('');
  }, [load]);

  const openInfo = async (name: string) => {
    if (!CLI_NAME_RE.test(name)) return;
    setBusy(true);
    setCopied(false);
    try {
      const next = await fetchCliHub({ action: 'info', name });
      setPicked(next.items?.[0] ?? null);
      setError(next.ok ? null : next.detail || '查詢失敗');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const copyInstall = async (name: string) => {
    if (!CLI_NAME_RE.test(name)) return;
    try {
      await navigator.clipboard.writeText(`cli-hub install ${name}`);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div id="cli-anything-catalog" className="mt-3 border-t border-white/[0.06] pt-3">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-[12px] font-semibold text-[var(--console-ink)]">CLI-Anything 目錄</h4>
        <span className="text-[10px] text-[var(--console-faint)]">
          {view?.version ? `cli-hub ${view.version}` : 'cli-hub'}
          {view ? ` · ${view.total} 個` : ''}
        </span>
      </div>
      <p className="mb-2 text-[11px] text-[var(--console-sub)]">
        {view?.note || '這裡只查目錄。安裝個別軟體需要另行確認。'}
      </p>
      {view && !view.hub_installed && (
        <p className="mb-2 font-mono text-[10px] text-amber-300">pip install cli-anything-hub==0.4.1</p>
      )}
      <form
        className="mb-2 flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void load(query);
        }}
      >
        <input
          className={inputCls}
          value={query}
          placeholder="搜尋名稱、說明或分類"
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="submit" className={btnCls} disabled={busy}>搜尋</button>
        <button type="button" className={btnCls} disabled={busy} onClick={() => { setQuery(''); void load(''); }}>
          全部
        </button>
      </form>
      {error && <p className="mb-2 text-[11px] console-status-danger">{error}</p>}
      {view?.detail && <p className="mb-2 text-[10px] text-[var(--console-faint)]">{view.detail}</p>}
      {query.trim() ? (
        <ul className="max-h-64 space-y-1 overflow-auto">
          {(view?.items ?? []).map((item) => (
            <li key={item.name}>
              <button type="button" className="w-full rounded px-1 py-1 text-left hover:bg-white/[0.04]" onClick={() => void openInfo(item.name)}>
                <span className="text-[12px] text-[var(--console-ink)]">{item.name}</span>
                <span className="ml-2 text-[10px] text-[var(--console-faint)]">{item.category}</span>
                {item.installed && <span className="ml-2 text-[10px] console-status-green">已安裝</span>}
                <span className="mt-0.5 block truncate text-[11px] text-[var(--console-sub)]">{item.description}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="max-h-72 space-y-2 overflow-auto">
          {(view?.categories ?? []).map((group) => (
            <div key={group.category}>
              <p className="mb-1 text-[10px] text-[var(--console-faint)]">
                {group.category} · {group.count}
              </p>
              <div className="flex flex-wrap gap-1">
                {group.names.filter((name) => CLI_NAME_RE.test(name)).map((name) => (
                  <button
                    key={name}
                    type="button"
                    className="rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] text-[var(--console-sub)] hover:text-[var(--console-ink)]"
                    onClick={() => void openInfo(name)}
                  >
                    {name}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {picked && (
        <div className="mt-2 rounded-lg border border-white/[0.06] bg-black/20 p-2.5">
          <p className="text-[12px] text-[var(--console-ink)]">{picked.display_name || picked.name}</p>
          <p className="mt-1 text-[11px] text-[var(--console-sub)]">{picked.description}</p>
          <p className="mt-1 text-[10px] text-[var(--console-faint)]">
            {picked.category} · {picked.version || '版本未標'} · {picked.installed ? '本機已安裝' : '本機尚未安裝'}
          </p>
          {picked.homepage && (
            <a className="mt-1 block truncate text-[10px] console-status-blue" href={picked.homepage} target="_blank" rel="noreferrer">
              {picked.homepage}
            </a>
          )}
          <button type="button" className={`${btnCls} mt-2`} onClick={() => void copyInstall(picked.name)}>
            {copied ? '已複製，安裝前請再確認' : '複製安裝命令，安裝前請再確認'}
          </button>
        </div>
      )}
    </div>
  );
}

export function CliRuntimeStrip() {
  const [rows, setRows] = useState<CliRuntimeStatus[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await fetchCliRuntimes());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const copyInstall = async (row: CliRuntimeStatus) => {
    try {
      await navigator.clipboard.writeText(row.install);
      setCopied(row.id);
    } catch {
      setCopied(null);
    }
  };

  return (
    <section className={`${cardCls} mb-4`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-[11px] font-semibold text-[var(--console-sub)]">CLI 運行時</h3>
        <button type="button" className={btnCls} onClick={() => void load()}>重新檢查</button>
      </div>
      <p className="mb-3 text-[11px] text-[var(--console-sub)]">
        這些技能不是 MCP，要本機有對應命令才執行得了。這裡只檢查 PATH，不安裝，也不讀取 Cookie 或金鑰。CLI-Anything 的目錄列在下方，同樣只查詢。
      </p>
      {error && <p className="mb-2 text-[11px] console-status-danger">{error}</p>}
      <div className="grid gap-2 lg:grid-cols-3">
        {rows.map((row) => (
          <div key={row.id} id={`cli-runtime-${row.id}`} className="rounded-lg border border-white/[0.06] bg-black/20 p-2.5">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-[12px] text-[var(--console-ink)]">{row.title}</span>
              <span className={`text-[10px] ${row.installed ? 'console-status-green' : 'text-amber-300'}`}>
                {row.installed ? '已安裝' : '未安裝'}
              </span>
            </div>
            <p className="mb-1 text-[10px] text-[var(--console-faint)]">{row.group} · {row.binary}</p>
            <p className="mb-2 text-[11px] text-[var(--console-sub)]">{row.summary}</p>
            <p className="mb-2 break-all font-mono text-[10px] text-[var(--console-faint)]">{row.installed ? row.path : row.install}</p>
            {row.installed && <p className="mb-2 truncate text-[10px] text-[var(--console-faint)]">{row.detail}</p>}
            {!row.installed && (
              <button type="button" className={btnCls} onClick={() => void copyInstall(row)}>
                {copied === row.id ? '已複製安裝命令' : '複製安裝命令'}
              </button>
            )}
          </div>
        ))}
      </div>
      <CliHubCatalog />
    </section>
  );
}
