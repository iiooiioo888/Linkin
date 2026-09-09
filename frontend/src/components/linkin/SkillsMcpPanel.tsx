/**
 * SkillsMcpPanel — 技能庫與 MCP 連線管理。
 *
 * 技能 = 注入角色提示詞的可重用知識（方法論／流程／領域指引）。
 * MCP  = 通用 Model Context Protocol server 連線（stdio/sse/http），
 *        探測後工具自動掛進公司工具註冊表，角色可經 tool_call 閉環調用。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  callMcpTool,
  deleteMcpServer,
  deleteSkill,
  fetchMcpServers,
  fetchSkills,
  mountMcpTools,
  previewSkillPrompt,
  probeMcpServer,
  saveMcpServer,
  saveSkill,
  toggleMcpServer,
  toggleSkill,
  type McpServerRecord,
  type SkillRecord,
} from '../../api/client';

type SubTab = 'skills' | 'mcp';

const inputCls =
  'w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[#F5F5F7] outline-none focus:border-[#64D2FF]/50';
const btnCls =
  'rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2.5 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8] disabled:opacity-40';
const btnPrimaryCls =
  'rounded-xl border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-2.5 py-1 text-[11px] text-[#64D2FF] disabled:opacity-40';
const cardCls = 'rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3';

function ErrorBar({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{message}</div>;
}

function OkBar({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{message}</div>;
}

// ══════════════ 技能庫 ══════════════

const EMPTY_SKILL_FORM = {
  id: '' as string,
  name: '',
  description: '',
  trigger: '',
  content: '',
  roles: '',
  enabled: true,
  skill_budget: 2400,
};

function SkillsSection() {
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [form, setForm] = useState({ ...EMPTY_SKILL_FORM });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSkills(await fetchSkills());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startEdit = (s: SkillRecord) => {
    setEditing(true);
    setForm({
      id: s.id,
      name: s.name,
      description: s.description,
      trigger: s.trigger,
      content: s.content,
      roles: s.roles.join(', '),
      enabled: s.enabled,
      skill_budget: s.skill_budget,
    });
  };

  const resetForm = () => {
    setEditing(false);
    setForm({ ...EMPTY_SKILL_FORM });
  };

  const onSave = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveSkill({
        id: form.id || null,
        name: form.name,
        content: form.content,
        description: form.description,
        trigger: form.trigger,
        roles: form.roles.split(',').map((r) => r.trim()).filter(Boolean),
        enabled: form.enabled,
        skill_budget: Number(form.skill_budget) || 2400,
      });
      setMessage(`已保存技能「${saved.name}」`);
      resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onToggle = async (s: SkillRecord) => {
    setError(null);
    try {
      await toggleSkill(s.id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onDelete = async (s: SkillRecord) => {
    setError(null);
    try {
      await deleteSkill(s.id);
      setMessage(`已刪除「${s.name}」`);
      if (form.id === s.id) resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onPreview = async () => {
    setError(null);
    try {
      const data = await previewSkillPrompt();
      setPreview(data.prompt || '（目前無啟用技能，注入區塊為空）');
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <div>
      <ErrorBar message={error} />
      <OkBar message={message} />

      <div className="mb-4 flex items-center justify-between">
        <p className="text-[11px] text-[#8a8f98]">
          技能會注入角色的系統提示詞（參考資料區塊）；停用即不注入。共 {skills.length} 條，啟用 {skills.filter((s) => s.enabled).length} 條。
        </p>
        <div className="flex gap-2">
          <button type="button" className={btnCls} onClick={() => void onPreview()}>預覽注入區塊</button>
          <button type="button" className={btnCls} onClick={() => void load()}>重新整理</button>
          {!editing && (
            <button type="button" className={btnPrimaryCls} onClick={() => { resetForm(); setEditing(true); }}>＋ 新技能</button>
          )}
        </div>
      </div>

      {preview !== null && (
        <div className="mb-4">
          <pre className="max-h-48 overflow-auto rounded-xl border border-white/[0.08] bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-[#AEAEB2]">{preview}</pre>
          <button type="button" className={`${btnCls} mt-1`} onClick={() => setPreview(null)}>收起預覽</button>
        </div>
      )}

      {editing && (
        <section className={`${cardCls} mb-4`}>
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">
            {form.id ? `編輯技能 · ${form.id}` : '新增技能'}
          </h3>
          <div className="grid gap-2 lg:grid-cols-2">
            <label className="text-[10px] text-[#8a8f98]">名稱 *
              <input className={`${inputCls} mt-1`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：部署更新流程" />
            </label>
            <label className="text-[10px] text-[#8a8f98]">適用時機（trigger）
              <input className={`${inputCls} mt-1`} value={form.trigger} onChange={(e) => setForm({ ...form, trigger: e.target.value })} placeholder="何時該用這條技能" />
            </label>
            <label className="text-[10px] text-[#8a8f98] lg:col-span-2">說明
              <input className={`${inputCls} mt-1`} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <label className="text-[10px] text-[#8a8f98] lg:col-span-2">內容 *（注入提示詞的知識本體）
              <textarea className={`${inputCls} mt-1 min-h-[140px] font-mono`} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="方法論／步驟／注意事項…" />
            </label>
            <label className="text-[10px] text-[#8a8f98]">限定角色（逗號分隔，留空＝全角色）
              <input className={`${inputCls} mt-1`} value={form.roles} onChange={(e) => setForm({ ...form, roles: e.target.value })} placeholder="developer, reviewer, custom_linkin_*" />
            </label>
            <div className="flex items-end gap-4">
              <label className="text-[10px] text-[#8a8f98]">單技能字元上限
                <input type="number" className={`${inputCls} mt-1 w-28`} value={form.skill_budget} onChange={(e) => setForm({ ...form, skill_budget: Number(e.target.value) })} />
              </label>
              <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[#AEAEB2]">
                <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                啟用
              </label>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" className={btnPrimaryCls} disabled={busy || !form.name.trim() || !form.content.trim()} onClick={() => void onSave()}>
              {busy ? '保存中…' : '保存'}
            </button>
            <button type="button" className={btnCls} onClick={resetForm}>取消</button>
          </div>
        </section>
      )}

      <div className="grid gap-2 lg:grid-cols-2">
        {skills.map((s) => (
          <div key={s.id} className={`${cardCls} ${s.enabled ? '' : 'opacity-50'}`}>
            <div className="mb-1 flex items-start justify-between gap-2">
              <div>
                <p className="text-[13px] font-medium text-[#F5F5F7]">{s.name}</p>
                <p className="font-mono text-[10px] text-[#636366]">{s.id}</p>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${s.enabled ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/[0.06] text-[#636366]'}`}>
                {s.enabled ? '啟用' : '停用'}
              </span>
            </div>
            {s.description && <p className="mb-1 text-[11px] text-[#8a8f98]">{s.description}</p>}
            {s.trigger && <p className="mb-1 text-[10px] text-[#64D2FF]/80">適用：{s.trigger}</p>}
            <pre className="mb-2 max-h-24 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-2 font-mono text-[10px] leading-relaxed text-[#8a8f98]">{s.content}</pre>
            <p className="mb-2 text-[10px] text-[#636366]">
              角色：{s.roles.length ? s.roles.join(', ') : '全部'} · 上限 {s.skill_budget} 字 · 更新 {s.updated_at ? s.updated_at.slice(0, 16).replace('T', ' ') : '—'}
            </p>
            <div className="flex gap-2">
              <button type="button" className={btnCls} onClick={() => startEdit(s)}>編輯</button>
              <button type="button" className={btnCls} onClick={() => void onToggle(s)}>{s.enabled ? '停用' : '啟用'}</button>
              <button type="button" className={`${btnCls} text-red-400/80 hover:text-red-300`} onClick={() => void onDelete(s)}>刪除</button>
            </div>
          </div>
        ))}
        {skills.length === 0 && !editing && (
          <p className="col-span-full py-8 text-center text-[12px] text-[#636366]">
            尚無技能。點「＋ 新技能」新增第一條——例如把公司的 SOP、代碼規範、領域知識放進去，角色執行時就會自動帶上。
          </p>
        )}
      </div>
    </div>
  );
}

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

function McpSection() {
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

  return (
    <div>
      <ErrorBar message={error} />
      <OkBar message={message} />

      <div className="mb-4 flex items-center justify-between">
        <p className="text-[11px] text-[#8a8f98]">
          通用 MCP 客戶端：stdio（本地子行程）／sse／http。探測成功後工具以 <code className="font-mono text-[#64D2FF]/80">server__tool</code> 掛進工具註冊表，角色即可調用。
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
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">
            {form.id ? `編輯連線 · ${form.id}` : '新增 MCP Server'}
          </h3>
          <div className="grid gap-2 lg:grid-cols-2">
            <label className="text-[10px] text-[#8a8f98]">名稱 *
              <input className={`${inputCls} mt-1`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：filesystem / github" />
            </label>
            <label className="text-[10px] text-[#8a8f98]">傳輸
              <select className={`${inputCls} mt-1`} value={form.transport} onChange={(e) => setForm({ ...form, transport: e.target.value as 'stdio' | 'sse' | 'http' })}>
                <option value="stdio">stdio（本地子行程）</option>
                <option value="sse">sse（Server-Sent Events）</option>
                <option value="http">http（streamable HTTP）</option>
              </select>
            </label>
            {form.transport === 'stdio' ? (
              <>
                <label className="text-[10px] text-[#8a8f98] lg:col-span-2">啟動命令 *
                  <input className={`${inputCls} mt-1 font-mono`} value={form.command} onChange={(e) => setForm({ ...form, command: e.target.value })} placeholder="npx -y @modelcontextprotocol/server-filesystem /data" />
                </label>
                <label className="text-[10px] text-[#8a8f98] lg:col-span-2">環境變數（每行 KEY=***
                  <textarea className={`${inputCls} mt-1 min-h-[52px] font-mono`} value={form.envText} onChange={(e) => setForm({ ...form, envText: e.target.value })} placeholder={'API_TOKEN=***'} />
                </label>
              </>
            ) : (
              <>
                <label className="text-[10px] text-[#8a8f98] lg:col-span-2">端點 URL *
                  <input className={`${inputCls} mt-1 font-mono`} value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://example.com/mcp" />
                </label>
                <label className="text-[10px] text-[#8a8f98] lg:col-span-2">自訂標頭（每行 KEY=***
                  <textarea className={`${inputCls} mt-1 min-h-[52px] font-mono`} value={form.headersText} onChange={(e) => setForm({ ...form, headersText: e.target.value })} placeholder={'X-Api-Key=***'} />
                </label>
              </>
            )}
            <label className="text-[10px] text-[#8a8f98]">工具白名單（逗號分隔，留空＝全部）
              <input className={`${inputCls} mt-1`} value={form.allowed_tools} onChange={(e) => setForm({ ...form, allowed_tools: e.target.value })} placeholder="search, read" />
            </label>
            <div className="flex items-end gap-4">
              <label className="text-[10px] text-[#8a8f98]">逾時（秒）
                <input type="number" className={`${inputCls} mt-1 w-24`} value={form.timeout} onChange={(e) => setForm({ ...form, timeout: Number(e.target.value) })} />
              </label>
              <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[#AEAEB2]">
                <input type="checkbox" checked={form.readonly} onChange={(e) => setForm({ ...form, readonly: e.target.checked })} />
                唯讀工具
              </label>
              <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[#AEAEB2]">
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
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">
            手動呼叫 · {callBox.server} / {callBox.tool}
          </h3>
          <label className="text-[10px] text-[#8a8f98]">參數（JSON）
            <textarea className={`${inputCls} mt-1 min-h-[60px] font-mono`} value={callBox.args} onChange={(e) => setCallBox({ ...callBox, args: e.target.value })} placeholder='{"query": "hello"}' />
          </label>
          <div className="mt-2 flex gap-2">
            <button type="button" className={btnPrimaryCls} disabled={busy === 'call'} onClick={() => void onCall()}>
              {busy === 'call' ? '呼叫中…' : '呼叫'}
            </button>
            <button type="button" className={btnCls} onClick={() => { setCallBox(null); setCallResult(null); }}>關閉</button>
          </div>
          {callResult !== null && (
            <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-black/40 p-2 font-mono text-[11px] leading-relaxed text-[#AEAEB2]">{callResult}</pre>
          )}
        </section>
      )}

      <div className="grid gap-2 lg:grid-cols-2">
        {servers.map((s) => {
          const probe = s.last_probe as { ok?: boolean; tool_count?: number; tools?: string[]; latency_ms?: number; error?: string; probed_at?: string } | undefined;
          return (
            <div key={s.id} className={`${cardCls} ${s.enabled ? '' : 'opacity-50'}`}>
              <div className="mb-1 flex items-start justify-between gap-2">
                <div>
                  <p className="text-[13px] font-medium text-[#F5F5F7]">{s.name}</p>
                  <p className="font-mono text-[10px] text-[#636366]">{s.id} · {s.transport}</p>
                </div>
                <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${s.enabled ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/[0.06] text-[#636366]'}`}>
                  {s.enabled ? '啟用' : '停用'}
                </span>
              </div>
              <p className="mb-1 break-all font-mono text-[10px] text-[#8a8f98]">
                {s.transport === 'stdio' ? s.command : s.url}
              </p>
              {probe && probe.probed_at ? (
                probe.ok ? (
                  <p className="mb-1 text-[10px] text-emerald-400/90">
                    ✓ 探測正常 · {probe.tool_count} 工具 · {probe.latency_ms}ms
                    {probe.tools && probe.tools.length > 0 && (
                      <span className="text-[#636366]">（{probe.tools.slice(0, 6).join(', ')}{probe.tools.length > 6 ? '…' : ''}）</span>
                    )}
                  </p>
                ) : (
                  <p className="mb-1 text-[10px] text-red-400/90">✗ {probe.error}</p>
                )
              ) : (
                <p className="mb-1 text-[10px] text-[#636366]">尚未探測</p>
              )}
              <p className="mb-2 text-[10px] text-[#636366]">
                白名單：{s.allowed_tools.length ? s.allowed_tools.join(', ') : '全部'} · {s.readonly ? '唯讀' : '可寫入'} · 逾時 {s.timeout}s
              </p>
              <div className="flex flex-wrap gap-2">
                <button type="button" className={btnCls} disabled={busy === `probe:${s.id}`} onClick={() => void onProbe(s)}>
                  {busy === `probe:${s.id}` ? '探測中…' : '探測'}
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
                <button type="button" className={`${btnCls} text-red-400/80 hover:text-red-300`} onClick={() => void onDelete(s)}>刪除</button>
              </div>
            </div>
          );
        })}
        {servers.length === 0 && !editing && (
          <p className="col-span-full py-8 text-center text-[12px] text-[#636366]">
            尚無 MCP 連線。點「＋ 新連線」接入第一個 server——例如 <code className="font-mono text-[#8a8f98]">npx -y @modelcontextprotocol/server-filesystem /data</code>。
          </p>
        )}
      </div>
    </div>
  );
}

export default function SkillsMcpPanel() {
  const [tab, setTab] = useState<SubTab>('skills');
  return (
    <div className="min-h-0 flex-1 overflow-y-auto p-5">
      <div className="mx-auto w-full max-w-5xl">
        <div className="mb-4 flex items-center gap-4">
          <h2 className="text-[15px] font-semibold text-[#F5F5F7]">技能與 MCP</h2>
          <div className="flex gap-1 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-0.5">
            <button
              type="button"
              className={`rounded-lg px-3 py-1 text-[11px] ${tab === 'skills' ? 'bg-[#64D2FF]/15 text-[#64D2FF]' : 'text-[#8a8f98] hover:text-[#F5F5F7]'}`}
              onClick={() => setTab('skills')}
            >
              技能庫
            </button>
            <button
              type="button"
              className={`rounded-lg px-3 py-1 text-[11px] ${tab === 'mcp' ? 'bg-[#64D2FF]/15 text-[#64D2FF]' : 'text-[#8a8f98] hover:text-[#F5F5F7]'}`}
              onClick={() => setTab('mcp')}
            >
              MCP 連線
            </button>
          </div>
        </div>
        {tab === 'skills' ? <SkillsSection /> : <McpSection />}
      </div>
    </div>
  );
}
