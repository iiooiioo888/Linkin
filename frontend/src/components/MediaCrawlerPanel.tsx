/**
 * MediaCrawler 採集控制台 — 配置、任務、結果瀏覽。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchMediaCrawlerJob,
  fetchMediaCrawlerJobs,
  fetchMediaCrawlerStatus,
  mediaCrawlerResultUrl,
  startMediaCrawlerJob,
  updateMediaCrawlerConfig,
  validateMediaCrawlerJob,
  type MediaCrawlerJobRecord,
  type MediaCrawlerStatus,
} from '../api/client';
import { consoleLayout } from './ui/ConsoleLayout';

const inputCls =
  'w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[var(--console-ink)] outline-none focus:border-[var(--console-blue)]/50';
const btnCls =
  'rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-2.5 py-1 text-[11px] text-[var(--console-sub)] hover:text-[var(--console-ink)] disabled:opacity-40';
const btnPrimaryCls =
  'rounded-xl border border-[var(--console-blue)]/40 bg-[var(--console-blue)]/10 px-2.5 py-1 text-[11px] console-status-blue disabled:opacity-40';
const cardCls = consoleLayout.insetCard;

const PLATFORM_LABELS: Record<string, string> = {
  xhs: '小紅書',
  dy: '抖音',
  ks: '快手',
  bili: 'B站',
  wb: '微博',
  tieba: '貼吧',
  zhihu: '知乎',
};

const TYPE_LABELS: Record<string, string> = {
  search: '關鍵詞搜尋',
  detail: '帖子詳情',
  creator: '創作者主頁',
};

function tierLabel(tier: MediaCrawlerStatus['tier'], cookieConfigured: boolean): string {
  if (tier === 'enabled' && cookieConfigured) return '已啟用';
  if (tier === 'available' || !cookieConfigured) return '可用（需配置）';
  return '需配置';
}

function tierTone(tier: MediaCrawlerStatus['tier'], cookieConfigured: boolean): string {
  if (tier === 'enabled' && cookieConfigured) return 'bg-emerald-500/15 text-emerald-400';
  if (tier === 'available' || !cookieConfigured) return 'bg-amber-500/15 text-amber-300';
  return 'bg-amber-500/15 text-amber-300';
}

function statusTone(status: string): string {
  if (status === 'completed') return 'text-emerald-400';
  if (status === 'running' || status === 'pending' || status === 'validating') return 'text-sky-300';
  if (status === 'failed') return 'text-red-400';
  return 'text-[var(--console-faint)]';
}

const EMPTY_FORM = {
  platform: 'xhs',
  crawl_type: 'search',
  login_type: 'cookie',
  keywords: '',
  post_ids: '',
  creator_ids: '',
  enable_comments: false,
  save_format: 'json',
  max_notes: 20,
  dry_run: true,
};

export default function MediaCrawlerPanel() {
  const [status, setStatus] = useState<MediaCrawlerStatus | null>(null);
  const [jobs, setJobs] = useState<MediaCrawlerJobRecord[]>([]);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [cookieInput, setCookieInput] = useState('');
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<MediaCrawlerJobRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [st, jobList] = await Promise.all([fetchMediaCrawlerStatus(), fetchMediaCrawlerJobs(20)]);
      setStatus(st);
      setJobs(jobList);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJob(null);
      return;
    }
    void fetchMediaCrawlerJob(selectedJobId)
      .then(setSelectedJob)
      .catch((err) => setError((err as Error).message));
  }, [selectedJobId]);

  const platformOptions = useMemo(() => status?.platforms ?? Object.keys(PLATFORM_LABELS), [status]);
  const typeOptions = useMemo(() => status?.crawl_types ?? Object.keys(TYPE_LABELS), [status]);
  const cookieReady = Boolean(status?.cookie_configured);
  const canStartRealRun = cookieReady && Boolean(status?.enabled);
  const startDisabled = busy || (!form.dry_run && !canStartRealRun);
  const startBlockReason = !form.dry_run && !cookieReady
    ? '實際採集需先保存平台 Cookie。'
    : !form.dry_run && !status?.enabled
      ? 'EVOL_MEDIACRAWLER_ENABLED 未啟用，僅可乾跑校驗。'
      : '';

  const onSaveCookie = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await updateMediaCrawlerConfig(cookieInput);
      setMessage(`Cookie 已保存（${res.cookie_preview || '已配置'}）`);
      setCookieInput('');
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onValidate = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await validateMediaCrawlerJob(form);
      if (res.valid) {
        setMessage(`配置校驗通過${res.command?.length ? `：${res.command.join(' ')}` : ''}`);
      } else {
        setError(res.errors.join('；'));
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onStart = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const job = await startMediaCrawlerJob(form);
      setMessage(`任務已提交：${job.job_id}（${job.status}）`);
      setSelectedJobId(job.job_id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`${cardCls} mb-4`} data-testid="mediacrawler-panel">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">MediaCrawler 採集</h3>
          <p className="mt-0.5 text-[10px] text-[var(--console-faint)]">
            多平台公開社媒資料採集（Playwright 子進程編排）
          </p>
        </div>
        {status ? (
          <span className={`rounded px-2 py-0.5 text-[10px] font-semibold ${tierTone(status.tier, cookieReady)}`}>
            {tierLabel(status.tier, cookieReady)}
          </span>
        ) : null}
      </div>

      {status?.legal_notice ? (
        <p className="mb-3 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-[10px] leading-relaxed text-amber-200/90">
          {status.legal_notice}
        </p>
      ) : null}

      {error ? (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      ) : null}
      {message ? (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{message}</div>
      ) : null}

      {status ? (
        <div className="mb-3 grid gap-2 text-[10px] text-[var(--console-sub)] sm:grid-cols-2 lg:grid-cols-4">
          <p>安裝：{status.installation.installed ? `是（${status.installation.runner || 'python'}）` : status.installation.reason || '否'}</p>
          <p>啟用：{status.enabled ? '是' : '否（僅乾跑）'}</p>
          <p>Cookie：{status.cookie_configured ? status.cookie_preview : '未配置'}</p>
          <p>運行中：{status.running_jobs ?? 0} / {status.max_concurrent_jobs}</p>
        </div>
      ) : null}

      {status && !cookieReady ? (
        <p className="mb-3 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[10px] text-amber-200/90">
          尚未配置 Cookie — 可進行「乾跑校驗」；取消乾跑並保存 Cookie 後才能啟動實際採集任務。
        </p>
      ) : null}

      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <p className="text-[11px] font-semibold text-[var(--console-sub)]">運行時配置</p>
          <label className="block text-[10px] text-[var(--console-sub)]">
            Cookie（不寫入 Git）
            <input
              className={`${inputCls} mt-1 font-mono`}
              type="password"
              value={cookieInput}
              onChange={(e) => setCookieInput(e.target.value)}
              placeholder="平台 Cookie 字串"
            />
          </label>
          <button type="button" className={btnCls} disabled={busy || !cookieInput.trim()} onClick={() => void onSaveCookie()}>
            保存 Cookie
          </button>
        </div>

        <div className="space-y-2">
          <p className="text-[11px] font-semibold text-[var(--console-sub)]">採集參數</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="text-[10px] text-[var(--console-sub)]">
              平台
              <select className={`${inputCls} mt-1`} value={form.platform} onChange={(e) => setForm({ ...form, platform: e.target.value })}>
                {platformOptions.map((p) => (
                  <option key={p} value={p}>{PLATFORM_LABELS[p] || p}</option>
                ))}
              </select>
            </label>
            <label className="text-[10px] text-[var(--console-sub)]">
              類型
              <select className={`${inputCls} mt-1`} value={form.crawl_type} onChange={(e) => setForm({ ...form, crawl_type: e.target.value })}>
                {typeOptions.map((t) => (
                  <option key={t} value={t}>{TYPE_LABELS[t] || t}</option>
                ))}
              </select>
            </label>
            <label className="text-[10px] text-[var(--console-sub)] sm:col-span-2">
              關鍵詞（search）
              <input className={`${inputCls} mt-1`} value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
            </label>
            <label className="text-[10px] text-[var(--console-sub)] sm:col-span-2">
              帖子 ID（detail，逗號分隔）
              <input className={`${inputCls} mt-1`} value={form.post_ids} onChange={(e) => setForm({ ...form, post_ids: e.target.value })} />
            </label>
            <label className="text-[10px] text-[var(--console-sub)] sm:col-span-2">
              創作者 ID（creator，逗號分隔）
              <input className={`${inputCls} mt-1`} value={form.creator_ids} onChange={(e) => setForm({ ...form, creator_ids: e.target.value })} />
            </label>
            <label className="flex items-center gap-2 text-[10px] text-[var(--console-sub)]">
              <input type="checkbox" checked={form.enable_comments} onChange={(e) => setForm({ ...form, enable_comments: e.target.checked })} />
              採集評論
            </label>
            <label className="flex items-center gap-2 text-[10px] text-[var(--console-sub)]">
              <input type="checkbox" checked={form.dry_run} onChange={(e) => setForm({ ...form, dry_run: e.target.checked })} />
              乾跑校驗（不實際爬取）
            </label>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={btnCls} disabled={busy} onClick={() => void onValidate()}>校驗配置</button>
            <button type="button" className={btnPrimaryCls} disabled={startDisabled} onClick={() => void onStart()}>
              {form.dry_run ? '乾跑啟動' : '啟動任務'}
            </button>
            <button type="button" className={btnCls} disabled={busy} onClick={() => void load()}>重新整理</button>
          </div>
          {startBlockReason ? (
            <p className="text-[10px] text-amber-300/90">{startBlockReason}</p>
          ) : null}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div>
          <p className="mb-2 text-[11px] font-semibold text-[var(--console-sub)]">最近任務</p>
          <div className="max-h-56 overflow-auto rounded-lg border border-white/[0.06]">
            <table className="w-full text-left text-[10px]">
              <thead className="bg-white/[0.03] text-[var(--console-faint)]">
                <tr>
                  <th className="px-2 py-1">ID</th>
                  <th className="px-2 py-1">平台</th>
                  <th className="px-2 py-1">狀態</th>
                  <th className="px-2 py-1">操作</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.job_id} className="border-t border-white/[0.04]">
                    <td className="px-2 py-1 font-mono">{job.job_id.slice(0, 8)}</td>
                    <td className="px-2 py-1">{String((job.request as { platform?: string }).platform || '—')}</td>
                    <td className={`px-2 py-1 ${statusTone(job.status)}`}>{job.status}</td>
                    <td className="px-2 py-1">
                      <button type="button" className="text-[var(--console-blue)]" onClick={() => setSelectedJobId(job.job_id)}>詳情</button>
                    </td>
                  </tr>
                ))}
                {jobs.length === 0 ? (
                  <tr><td colSpan={4} className="px-2 py-3 text-center text-[var(--console-faint)]">尚無任務</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <p className="mb-2 text-[11px] font-semibold text-[var(--console-sub)]">任務詳情 / 結果</p>
          {!selectedJob ? (
            <p className={`${consoleLayout.emptySm} text-[11px] text-[var(--console-faint)]`}>選擇任務查看日誌與結果檔案</p>
          ) : (
            <div className="space-y-2">
              <p className="text-[10px] text-[var(--console-sub)]">
                {selectedJob.job_id} · <span className={statusTone(selectedJob.status)}>{selectedJob.status}</span>
                {selectedJob.error ? ` · ${selectedJob.error}` : ''}
              </p>
              {selectedJob.log_tail ? (
                <pre className="max-h-28 overflow-auto rounded-lg bg-black/40 p-2 font-mono text-[10px] text-[#AEAEB2]">{selectedJob.log_tail}</pre>
              ) : null}
              {selectedJob.results && selectedJob.results.length > 0 ? (
                <table className="w-full text-left text-[10px]">
                  <thead className="text-[var(--console-faint)]">
                    <tr><th className="px-1 py-1">檔案</th><th className="px-1 py-1">大小</th><th className="px-1 py-1">下載</th></tr>
                  </thead>
                  <tbody>
                    {selectedJob.results.map((f) => (
                      <tr key={f.name} className="border-t border-white/[0.04]">
                        <td className="px-1 py-1 font-mono">{f.name}</td>
                        <td className="px-1 py-1">{f.size}</td>
                        <td className="px-1 py-1">
                          <a className="console-status-blue" href={mediaCrawlerResultUrl(selectedJob.job_id, f.name)} target="_blank" rel="noopener noreferrer">下載</a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-[10px] text-[var(--console-faint)]">尚無結果檔案</p>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
