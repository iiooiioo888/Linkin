/**
 * MCP 連線分頁：server 卡片、探測、掛載工具、手動呼叫與新增／編輯表單。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  callMcpTool,
  deleteMcpServer,
  fetchMcpServers,
  mountMcpTools,
  probeMcpServer,
  saveMcpServer,
  toggleMcpServer,
  type McpServerRecord,
} from '../../api/client';
import { consoleLayout } from '../ui/ConsoleLayout';
import { ErrorBar, OkBar, TierSection } from './shared';
import { btnCls, btnPrimaryCls, cardCls, inputCls } from './styles';
import { mcpHealthLabel, mcpTierOf } from './tiers';

// ══════════════ MCP 連線 ══════════════

const EMPTY_MCP_FORM = {
  id: '',
  name: '',
  transport: 'stdio' as 'stdio' | 'sse' | 'http',
  command: '',
  envText: '',
  url: '',
  headersText: '',
  enabled: true,
  allowed_tools: '',
  readonly: true,
  timeout: 20,
};

function parseKv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split('\n')) {
    const idx = line.indexOf('=');
    if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return out;
}

function kvToText(kv: Record<string, string>): string {
  return Object.entries(kv ?? {}).map(([k, v]) => `${k}=${v}`).join('\n');
}

export function McpSection() {
  const { t } = useTranslation();
  const [servers, setServers] = useState<McpServerRecord[]>([]);
  const [form, setForm] = useState({ ...EMPTY_MCP_FORM });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [callBox, setCallBox] = useState<{ server: string; tool: string; args: string } | null>(null);
  const [callResult, setCallResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setServers(await fetchMcpServers());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startEdit = (s: McpServerRecord) => {
    setEditing(true);
    setForm({
      id: s.id,
      name: s.name,
      transport: s.transport,
      command: s.command,
      envText: kvToText(s.env),
      url: s.url,
      headersText: kvToText(s.headers),
      enabled: s.enabled,
      allowed_tools: s.allowed_tools.join(', '),
      readonly: s.readonly,
      timeout: s.timeout,
    });
  };

  const resetForm = () => {
    setEditing(false);
    setForm({ ...EMPTY_MCP_FORM });
  };

  const onSave = async () => {
    setBusy('save');
    setError(null);
    setMessage(null);
    try {
      const saved = await saveMcpServer({
        id: form.id || null,
        name: form.name,
        transport: form.transport,
        command: form.command,
        env: parseKv(form.envText),
        url: form.url,
        headers: parseKv(form.headersText),
        enabled: form.enabled,
        allowed_tools: form.allowed_tools.split(',').map((t) => t.trim()).filter(Boolean),
        readonly: form.readonly,
        timeout: Number(form.timeout) || 20,
      });
      setMessage(`已保存「${saved.name}」`);
      resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onProbe = async (s: McpServerRecord) => {
    setBusy(`probe:${s.id}`);
    setError(null);
    setMessage(null);
    try {
      const r = await probeMcpServer(s.id);
      if (r.ok) setMessage(`「${s.name}」連線正常：${r.tool_count} 個工具（${r.latency_ms}ms）`);
      else setError(`「${s.name}」探測失敗：${r.error}`);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onToggle = async (s: McpServerRecord) => {
    setError(null);
    try {
      await toggleMcpServer(s.id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onDelete = async (s: McpServerRecord) => {
    setError(null);
    try {
      await deleteMcpServer(s.id);
      setMessage(`已刪除「${s.name}」`);
      if (form.id === s.id) resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onMount = async () => {
    setBusy('mount');
    setError(null);
    setMessage(null);
    try {
      const r = await mountMcpTools();
      setMessage(r.count ? `已掛載 ${r.count} 個工具：${r.mounted.join(', ')}` : '沒有可掛載的工具（server 未啟用或探測失敗）');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const onCall = async () => {
    if (!callBox) return;
    setBusy('call');
    setError(null);
    setCallResult(null);
    try {
      const args = callBox.args.trim() ? JSON.parse(callBox.args) : {};
      const result = await callMcpTool(callBox.server, callBox.tool, args);
      setCallResult(result || '（空回應）');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const tiers = useMemo(() => ({
    enabled: servers.filter((s) => mcpTierOf(s) === 'enabled'),
    available: servers.filter((s) => mcpTierOf(s) === 'available'),
    needsKey: servers.filter((s) => mcpTierOf(s) === 'needsKey'),
  }), [servers]);

  const renderMcpCard = (s: McpServerRecord) => {
    const probe = s.last_probe as { ok?: boolean; tool_count?: number; tools?: string[]; latency_ms?: number; error?: string; probed_at?: string } | undefined;
    const health = mcpHealthLabel(s);
    return (
      <div key={s.id} className={`${cardCls} ${s.enabled ? '' : 'opacity-50'}`}>
        <div className="mb-1 flex items-start justify-between gap-2">
          <div>
            <p className="text-[13px] font-medium text-[var(--console-ink)]">{s.name}</p>
            <p className="font-mono text-[10px] text-[var(--console-faint)]">{s.id} · {s.transport}</p>
          </div>
          <div className="flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${health === 'ok' ? 'bg-[var(--console-green)]' : health === 'warn' ? 'bg-[var(--console-amber)]' : 'bg-[var(--console-faint)]'}`}
              title={health === 'ok' ? t('skills.mcpHealthOk') : health === 'warn' ? t('skills.mcpHealthWarn') : t('skills.mcpHealthUnknown')}
            />
            <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${s.enabled ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/[0.06] text-[var(--console-faint)]'}`}>
              {s.enabled ? t('skills.tierEnabled') : t('skills.tierAvailable')}
            </span>
          </div>
        </div>
        <p className="mb-1 break-all font-mono text-[10px] text-[var(--console-sub)]">
          {s.transport === 'stdio' ? s.command : s.url}
        </p>
        {probe && probe.probed_at ? (
          probe.ok ? (
            <p className="mb-1 text-[10px] text-emerald-400/90">
              ✓ {t('skills.mcpHealthOk')} · {probe.tool_count} 工具 · {probe.latency_ms}ms
            </p>
          ) : (
            <p className="mb-1 text-[10px] text-red-400/90">✗ {probe.error}</p>
          )
        ) : (
          <p className="mb-1 text-[10px] text-[var(--console-faint)]">{t('skills.mcpHealthUnknown')}</p>
        )}
        <p className="mb-2 text-[10px] text-[var(--console-faint)]">
          白名單：{s.allowed_tools.length ? s.allowed_tools.join(', ') : '全部'} · {s.readonly ? '唯讀' : '可寫入'} · 逾時 {s.timeout}s
        </p>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btnCls} disabled={busy === `probe:${s.id}`} onClick={() => void onProbe(s)}>
            {busy === `probe:${s.id}` ? '探測中…' : t('skills.mcpProbe')}
          </button>
          <button type="button" className={btnCls} onClick={() => startEdit(s)}>編輯</button>
          <button type="button" className={btnCls} onClick={() => void onToggle(s)}>{s.enabled ? '停用' : '啟用'}</button>
          {probe?.ok && (probe.tools ?? []).length > 0 && (
            <button
              type="button"
              className={btnCls}
              onClick={() => { setCallBox({ server: s.id, tool: (probe?.tools ?? [])[0], args: '{}' }); setCallResult(null); }}
            >
              呼叫工具
            </button>
          )}
          <button type="button" className={`${btnCls} text-red-400/80 hover:console-status-danger`} onClick={() => void onDelete(s)}>刪除</button>
        </div>
      </div>
    );
  };

  return (
    <div>
      <ErrorBar message={error} />
      <OkBar message={message} />

      <div className="mb-4 flex items-center justify-between">
        <p className="text-[11px] text-[var(--console-sub)]">
          通用 MCP 客戶端：stdio（本地子行程）／sse／http。探測成功後工具以 <code className="font-mono console-status-blue/80">server__tool</code> 掛進工具註冊表，角色即可調用。
        </p>
        <div className="flex gap-2">
          <button type="button" className={btnCls} disabled={busy === 'mount'} onClick={() => void onMount()}>
            {busy === 'mount' ? '掛載中…' : '重新掛載工具'}
          </button>
          <button type="button" className={btnCls} onClick={() => void load()}>重新整理</button>
          {!editing && (
            <button type="button" className={btnPrimaryCls} onClick={() => { resetForm(); setEditing(true); }}>＋ 新連線</button>
          )}
        </div>
      </div>

      {editing && (
        <section className={`${cardCls} mb-4`}>
          <h3 className="mb-2 text-[11px] font-semibold text-[var(--console-sub)]">
            {form.id ? `編輯連線 · ${form.id}` : '新增 MCP Server'}
          </h3>
          <div className="grid gap-2 lg:grid-cols-2">
            <label className="text-[10px] text-[var(--console-sub)]">名稱 *
              <input className={`${inputCls} mt-1`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：filesystem / github" />
            </label>
            <label className="text-[10px] text-[var(--console-sub)]">傳輸
              <select className={`${inputCls} mt-1`} value={form.transport} onChange={(e) => setForm({ ...form, transport: e.target.value as 'stdio' | 'sse' | 'http' })}>
                <option value="stdio">stdio（本地子行程）</option>
                <option value="sse">sse（Server-Sent Events）</option>
                <option value="http">http（streamable HTTP）</option>
              </select>
            </label>
            {form.transport === 'stdio' ? (
              <>
                <label className="text-[10px] text-[var(--console-sub)] lg:col-span-2">啟動命令 *
                  <input className={`${inputCls} mt-1 font-mono`} value={form.command} onChange={(e) => setForm({ ...form, command: e.target.value })} placeholder="npx -y @modelcontextprotocol/server-filesystem /data" />
                </label>
                <label className="text-[10px] text-[var(--console-sub)] lg:col-span-2">環境變數（每行 KEY=***
                  <textarea className={`${inputCls} mt-1 min-h-[52px] font-mono`} value={form.envText} onChange={(e) => setForm({ ...form, envText: e.target.value })} placeholder={'API_TOKEN=***'} />
                </label>
              </>
            ) : (
              <>
                <label className="text-[10px] text-[var(--console-sub)] lg:col-span-2">端點 URL *
                  <input className={`${inputCls} mt-1 font-mono`} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://example.com/mcp" />
                </label>
                <label className="text-[10px] text-[var(--console-sub)] lg:col-span-2">自訂標頭（每行 KEY=***
                  <textarea className={`${inputCls} mt-1 min-h-[52px] font-mono`} value={form.headersText} onChange={(e) => setForm({ ...form, headersText: e.target.value })} placeholder={'X-Api-Key=***'} />
                </label>
              </>
            )}
            <label className="text-[10px] text-[var(--console-sub)]">工具白名單（逗號分隔，留空＝全部）
              <input className={`${inputCls} mt-1`} value={form.allowed_tools} onChange={(e) => setForm({ ...form, allowed_tools: e.target.value })} placeholder="search, read" />
            </label>
            <div className="flex items-end gap-4">
              <label className="text-[10px] text-[var(--console-sub)]">逾時（秒）
                <input type="number" className={`${inputCls} mt-1 w-24`} value={form.timeout} onChange={(e) => setForm({ ...form, timeout: Number(e.target.value) })} />
              </label>
              <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[var(--console-sub)]">
                <input type="checkbox" checked={form.readonly} onChange={(e) => setForm({ ...form, readonly: e.target.checked })} />
                唯讀工具
              </label>
              <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[var(--console-sub)]">
                <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                啟用
              </label>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              className={btnPrimaryCls}
              disabled={busy === 'save' || !form.name.trim() || (form.transport === 'stdio' ? !form.command.trim() : !form.url.trim())}
              onClick={() => void onSave()}
            >
              {busy === 'save' ? '保存中…' : '保存'}
            </button>
            <button type="button" className={btnCls} onClick={resetForm}>取消</button>
          </div>
        </section>
      )}

      {callBox && (
        <section className={`${cardCls} mb-4`}>
          <h3 className="mb-2 text-[11px] font-semibold text-[var(--console-sub)]">
            手動呼叫 · {callBox.server} / {callBox.tool}
          </h3>
          <label className="text-[10px] text-[var(--console-sub)]">參數（JSON）
            <textarea className={`${inputCls} mt-1 min-h-[60px] font-mono`} value={callBox.args} onChange={(e) => setCallBox({ ...callBox, args: e.target.value })} placeholder='{"query": "hello"}' />
          </label>
          <div className="mt-2 flex gap-2">
            <button type="button" className={btnPrimaryCls} disabled={busy === 'call'} onClick={() => void onCall()}>
              {busy === 'call' ? '呼叫中…' : '呼叫'}
            </button>
            <button type="button" className={btnCls} onClick={() => { setCallBox(null); setCallResult(null); }}>關閉</button>
          </div>
          {callResult !== null && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-black/40 p-2 font-mono text-[11px] leading-relaxed text-[var(--console-sub)]">{callResult}</pre>
          )}
        </section>
      )}

      <TierSection title={t('skills.tierEnabled')} count={tiers.enabled.length}>
        <div className="grid gap-2 lg:grid-cols-2">{tiers.enabled.map(renderMcpCard)}</div>
      </TierSection>
      <TierSection title={t('skills.tierAvailable')} count={tiers.available.length} defaultOpen={false}>
        <div className="grid gap-2 lg:grid-cols-2">{tiers.available.map(renderMcpCard)}</div>
      </TierSection>
      <TierSection title={t('skills.tierNeedsKey')} count={tiers.needsKey.length} defaultOpen={false}>
        <div className="grid gap-2 lg:grid-cols-2">{tiers.needsKey.map(renderMcpCard)}</div>
      </TierSection>
      {servers.length === 0 && !editing && (
        <p className={`${consoleLayout.emptySm} text-[12px] text-[var(--console-faint)]`}>
          尚無 MCP 連線。點「＋ 新連線」接入第一個 server——例如 <code className="font-mono text-[var(--console-sub)]">npx -y @modelcontextprotocol/server-filesystem /data</code>。
        </p>
      )}
    </div>
  );
}
