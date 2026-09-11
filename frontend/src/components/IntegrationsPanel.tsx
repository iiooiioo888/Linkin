/**
 * IntegrationsPanel — MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil 控制台。
 *
 * 契約對齊：
 * - 啟用為顯式開關（C-INTEG-002）
 * - 召回／任務／訪談／設計皆為按需動作；禁止自動灌入審計分數
 * - 側欄資訊預設折疊；審計結果不佔常駐分數槽（C-UI-001）
 * - 深鏈：#/monitor/integrations/{name} 聚焦對應卡片
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  fetchIntegrations,
  ouroborosAuto,
  ouroborosEvaluate,
  ouroborosInterview,
  openpencilGenerate,
  openpencilListProjects,
  runIntegrationRecall,
  toggleIntegration,
  yaoCreateTask,
  yaoListTasks,
  yaoListWorkspaces,
  type IntegrationGroup,
  type IntegrationStatus,
  type RecallResult,
} from '../api/integrations';
import IntegrationsStrip from './IntegrationsStrip';
import {
  GROUP_LABEL,
  INTEGRATION_META,
  jumpToIntegration,
  metaOf,
  parseIntegrationFocus,
  summarizeIntegrations,
  type IntegrationName,
} from '../lib/integrationsUi';
import { jumpToL0Kernel, jumpToContextMonitor } from '../lib/rahoUi';
import { openChatContextDetail } from '../lib/contextUi';
import { PanelSection, PanelShell, consoleLayout } from './ui/ConsoleLayout';

const inputCls =
  'w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[var(--console-ink)] outline-none focus:border-[var(--console-blue)]/50';
const btnCls =
  'rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2.5 py-1 text-[11px] text-[var(--console-sub)] hover:text-[var(--console-ink)] disabled:opacity-40';
const btnPrimaryCls =
  'rounded-xl border border-[var(--console-blue)]/40 bg-[var(--console-blue)]/10 px-2.5 py-1 text-[11px] console-status-blue disabled:opacity-40';
const cardCls = consoleLayout.insetCard;

function ErrorBar({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-3 rounded-md border border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-3 py-2 text-xs console-status-danger">
      {message}
    </div>
  );
}

function OkBar({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs console-status-green">
      {message}
    </div>
  );
}

function healthTone(item: IntegrationStatus): string {
  if (!item.enabled) return 'text-[var(--console-faint)]';
  if (item.health?.ok === false) return 'console-status-danger';
  return 'console-status-green';
}

function healthLabel(item: IntegrationStatus): string {
  if (!item.enabled) return '已停用';
  if (item.health?.ok === false) return item.health.reason_code || '不可達';
  const ms = item.health?.latency_ms;
  return typeof ms === 'number' ? `健康 · ${Math.round(ms)}ms` : '健康';
}

function JsonBlock({ value }: { value: unknown }) {
  if (value == null) return null;
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return (
    <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-white/[0.06] bg-black/40 p-2 text-[10px] leading-relaxed text-[#AEAEB2]">
      {text}
    </pre>
  );
}

function IntegrationCard({
  item,
  busy,
  focused,
  forceOpen,
  onToggle,
  children,
}: {
  item: IntegrationStatus;
  busy: boolean;
  focused?: boolean;
  forceOpen?: boolean;
  onToggle: (enabled: boolean) => void;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(Boolean(forceOpen));
  const ref = useRef<HTMLElement>(null);
  const meta = metaOf(item.name);

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
        <label className="flex shrink-0 cursor-pointer items-center gap-2 text-[11px] text-[#AEAEB2]">
          <span>{item.enabled ? '啟用' : '關閉'}</span>
          <input
            type="checkbox"
            className="accent-[#64D2FF]"
            checked={item.enabled}
            disabled={busy}
            onChange={(e) => onToggle(e.target.checked)}
          />
        </label>
      </div>
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

function RecallWorkbench({ enabled }: { enabled: boolean }) {
  const [query, setQuery] = useState('當前任務目標與約束');
  const [kbId, setKbId] = useState('');
  const [cubeIds, setCubeIds] = useState('default');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecallResult | null>(null);

  const run = async () => {
    if (!enabled) return;
    setBusy(true);
    setError(null);
    try {
      const out = await runIntegrationRecall({
        query,
        cube_ids: cubeIds
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        knowledge_base_id: kbId,
      });
      setResult(out);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={cardCls}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">召回試跑</h3>
          <p className="text-[11px] text-[var(--console-sub)]">MemOS ＋ OpenViking ＋ WeKnora → 注入片段（不經 LLM）</p>
        </div>
        <button type="button" className="text-[11px] text-[#0A84FF]" onClick={jumpToL0Kernel}>
          開啟 L0 核心 →
        </button>
      </div>
      <ErrorBar message={error} />
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="block text-[10px] text-[var(--console-sub)]">
          查詢
          <textarea className={`${inputCls} mt-1 min-h-[64px]`} value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <div className="space-y-2">
          <label className="block text-[10px] text-[var(--console-sub)]">
            MemOS cube IDs（逗號分隔）
            <input className={`${inputCls} mt-1`} value={cubeIds} onChange={(e) => setCubeIds(e.target.value)} />
          </label>
          <label className="block text-[10px] text-[var(--console-sub)]">
            WeKnora knowledge_base_id
            <input className={`${inputCls} mt-1`} value={kbId} onChange={(e) => setKbId(e.target.value)} />
          </label>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button type="button" className={btnPrimaryCls} disabled={!enabled || busy || !query.trim()} onClick={() => void run()}>
          {busy ? '召回中…' : '執行召回'}
        </button>
      </div>
      {!enabled ? <p className="mt-2 text-[10px] text-[var(--console-faint)]">請先啟用至少一個召回類整合。</p> : null}
      {result ? (
        <div className="mt-3 space-y-2">
          <div className="flex flex-wrap gap-2 text-[10px] text-[#AEAEB2]">
            <span>原因碼 {result.reason_codes?.length ?? 0}</span>
            <span>降級來源 {(result.degraded_sources ?? []).join(', ') || '無'}</span>
          </div>
          <JsonBlock value={result.token_report} />
          <JsonBlock value={result.injection || result.fragments} />
        </div>
      ) : null}
    </section>
  );
}

function YaoActions() {
  const [workspaceId, setWorkspaceId] = useState('');
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [payload, setPayload] = useState<unknown>(null);

  const run = async (fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const out = await fn();
      setPayload(out);
      const ok = typeof out === 'object' && out && 'ok' in out ? Boolean((out as { ok: boolean }).ok) : true;
      if (!ok) {
        const code =
          typeof out === 'object' && out && 'error_code' in out
            ? String((out as { error_code?: string }).error_code || 'ERR')
            : 'ERR';
        setError(code);
      } else {
        setMessage(okMsg);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <ErrorBar message={error} />
      <OkBar message={message} />
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnCls} disabled={busy} onClick={() => void run(() => yaoListWorkspaces(), '已列出工作區')}>
          列出工作區
        </button>
        <button
          type="button"
          className={btnCls}
          disabled={busy || !workspaceId.trim()}
          onClick={() => void run(() => yaoListTasks(workspaceId.trim()), '已列出任務')}
        >
          列出任務
        </button>
      </div>
      <label className="block text-[10px] text-[var(--console-sub)]">
        workspace_id
        <input className={`${inputCls} mt-1`} value={workspaceId} onChange={(e) => setWorkspaceId(e.target.value)} />
      </label>
      <label className="block text-[10px] text-[var(--console-sub)]">
        任務標題
        <input className={`${inputCls} mt-1`} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="block text-[10px] text-[var(--console-sub)]">
        任務 prompt
        <textarea className={`${inputCls} mt-1 min-h-[56px]`} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </label>
      <button
        type="button"
        className={btnPrimaryCls}
        disabled={busy || !workspaceId.trim() || !title.trim() || !prompt.trim()}
        onClick={() =>
          void run(
            () =>
              yaoCreateTask({
                workspace_id: workspaceId.trim(),
                title: title.trim(),
                prompt: prompt.trim(),
              }),
            '任務已建立（顯式）',
          )
        }
      >
        建立任務
      </button>
      <JsonBlock value={payload} />
    </div>
  );
}

function OuroborosActions() {
  const [goal, setGoal] = useState('');
  const [ambiguity, setAmbiguity] = useState('0.15');
  const [force, setForce] = useState(false);
  const [executionId, setExecutionId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [payload, setPayload] = useState<unknown>(null);

  const run = async (fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const out = await fn();
      setPayload(out);
      const obj = out as { ok?: boolean; allowed?: boolean; error_code?: string };
      if (obj.ok === false || obj.allowed === false) {
        setError(obj.error_code || '閘門阻擋或失敗');
      } else {
        setMessage(okMsg);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <ErrorBar message={error} />
      <OkBar message={message} />
      <label className="block text-[10px] text-[var(--console-sub)]">
        目標 goal
        <textarea className={`${inputCls} mt-1 min-h-[56px]`} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </label>
      <div className="flex flex-wrap items-end gap-2">
        <label className="block text-[10px] text-[var(--console-sub)]">
          ambiguity（≤0.2 才准 Seed）
          <input className={`${inputCls} mt-1 w-28`} value={ambiguity} onChange={(e) => setAmbiguity(e.target.value)} />
        </label>
        <label className="flex items-center gap-1.5 pb-1 text-[11px] text-[#AEAEB2]">
          <input type="checkbox" className="accent-[#64D2FF]" checked={force} onChange={(e) => setForce(e.target.checked)} />
          force 繞過閘門
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={btnCls}
          disabled={busy || !goal.trim()}
          onClick={() => void run(() => ouroborosInterview(goal.trim()), '訪談完成')}
        >
          訪談
        </button>
        <button
          type="button"
          className={btnPrimaryCls}
          disabled={busy || !goal.trim()}
          onClick={() =>
            void run(
              () =>
                ouroborosAuto({
                  goal: goal.trim(),
                  ambiguity: Number(ambiguity) || 0,
                  force,
                }),
              'auto 已啟動',
            )
          }
        >
          啟動 auto
        </button>
      </div>
      <label className="block text-[10px] text-[var(--console-sub)]">
        execution_id（評估）
        <input className={`${inputCls} mt-1`} value={executionId} onChange={(e) => setExecutionId(e.target.value)} />
      </label>
      <button
        type="button"
        className={btnCls}
        disabled={busy || !executionId.trim()}
        onClick={() => void run(() => ouroborosEvaluate(executionId.trim()), '三階段評估完成')}
      >
        執行評估
      </button>
      <JsonBlock value={payload} />
    </div>
  );
}

function OpenPencilActions() {
  const [prompt, setPrompt] = useState('');
  const [style, setStyle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [payload, setPayload] = useState<unknown>(null);

  const run = async (fn: () => Promise<unknown>, okMsg: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const out = await fn();
      setPayload(out);
      const ok = typeof out === 'object' && out && 'ok' in out ? Boolean((out as { ok: boolean }).ok) : true;
      if (!ok) {
        setError(String((out as { error_code?: string }).error_code || '失敗'));
      } else {
        setMessage(okMsg);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <ErrorBar message={error} />
      <OkBar message={message} />
      <button type="button" className={btnCls} disabled={busy} onClick={() => void run(() => openpencilListProjects(), '已列出專案')}>
        列出專案
      </button>
      <label className="block text-[10px] text-[var(--console-sub)]">
        設計 prompt
        <textarea className={`${inputCls} mt-1 min-h-[56px]`} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      </label>
      <label className="block text-[10px] text-[var(--console-sub)]">
        style（可選）
        <input className={`${inputCls} mt-1`} value={style} onChange={(e) => setStyle(e.target.value)} />
      </label>
      <button
        type="button"
        className={btnPrimaryCls}
        disabled={busy || !prompt.trim()}
        onClick={() =>
          void run(
            () => openpencilGenerate({ prompt: prompt.trim(), style: style.trim() || undefined }),
            '設計生成已觸發（顯式）',
          )
        }
      >
        生成設計
      </button>
      <JsonBlock value={payload} />
    </div>
  );
}

export default function IntegrationsPanel() {
  const [items, setItems] = useState<IntegrationStatus[]>([]);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [focus, setFocus] = useState<IntegrationName | null>(() => parseIntegrationFocus());

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await fetchIntegrations());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 12000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const onHash = () => setFocus(parseIntegrationFocus());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const byGroup = useMemo(() => {
    const order: IntegrationGroup[] = ['recall', 'agent', 'design'];
    return order.map((group) => ({
      group,
      meta: GROUP_LABEL[group],
      items: items.filter((i) => i.group === group),
    }));
  }, [items]);

  const recallEnabled = items.some((i) => i.group === 'recall' && i.enabled);
  const summary = summarizeIntegrations(items);

  const onToggle = async (name: string, enabled: boolean) => {
    setBusyName(name);
    setError(null);
    setMessage(null);
    try {
      const out = await toggleIntegration(name, enabled);
      if (!out.ok) {
        setError(out.error_code || '切換失敗');
      } else {
        setMessage(`${name} 已${enabled ? '啟用' : '停用'}（顯式動作）`);
        await load();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyName(null);
    }
  };

  const actionBody = (name: string) => {
    if (name === 'yao') return <YaoActions />;
    if (name === 'ouroboros') return <OuroborosActions />;
    if (name === 'openpencil') return <OpenPencilActions />;
    const meta = INTEGRATION_META[name as IntegrationName];
    return (
      <p className="text-[11px] text-[var(--console-sub)]">
        {meta?.hint || '此整合經「召回試跑」編排'}；亦可於 L0 核心面板查看注入結果。
      </p>
    );
  };

  return (
    <PanelShell>
      <PanelSection>
      <header className="integ-hero">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>外部整合運行時</h2>
            <p>
              MemOS · OpenViking · WeKnora · Yao · Ouroboros · OpenPencil。預設關閉；啟用與動作皆為顯式，fail-open
              不阻斷主任務。深鏈：
              <code className="ml-1 text-[10px] text-[#AEAEB2]">#/monitor/integrations/memos</code>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-white/[0.08] px-2.5 py-1 text-[10px] text-[#AEAEB2]">
              已啟用 {summary.enabled}/{summary.total}
              {summary.degraded ? ` · 降級 ${summary.degraded}` : ''}
            </span>
            <button type="button" className={btnCls} onClick={() => openChatContextDetail()}>
              Context 詳細區
            </button>
            <button type="button" className={btnCls} onClick={() => jumpToContextMonitor()}>
              Context 鏡像
            </button>
            <button type="button" className={btnCls} onClick={() => void load()}>
              重新整理
            </button>
          </div>
        </div>
        <IntegrationsStrip
          items={items}
          density="comfortable"
          showSummary={false}
          onFocus={(name) => {
            setFocus(name);
            jumpToIntegration(name);
          }}
        />
      </header>

      <ErrorBar message={error} />
      <OkBar message={message} />

      <div className="mb-4">
        <RecallWorkbench enabled={recallEnabled} />
      </div>

      <div className="space-y-4">
        {byGroup.map(({ group, meta, items: groupItems }) => (
          <section key={group}>
            <div className="mb-2">
              <h3 className="text-[12px] font-semibold tracking-wide text-[var(--console-ink)]">{meta.label}</h3>
              <p className="text-[10px] text-[var(--console-faint)]">{meta.hint}</p>
            </div>
            <div className={consoleLayout.cardGrid}>
              {groupItems.map((item) => (
                <IntegrationCard
                  key={item.name}
                  item={item}
                  busy={busyName === item.name}
                  focused={focus === item.name}
                  forceOpen={focus === item.name && item.enabled}
                  onToggle={(enabled) => void onToggle(item.name, enabled)}
                >
                  {actionBody(item.name)}
                </IntegrationCard>
              ))}
            </div>
          </section>
        ))}
      </div>
      </PanelSection>
    </PanelShell>
  );
}
