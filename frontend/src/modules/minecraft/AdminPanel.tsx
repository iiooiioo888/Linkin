/**
 * Minecraft Admin — 伺服器健康、批准隊列、巡檢與遊戲指令。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  askServerAdmin,
  cancelServerApproval,
  confirmServerApproval,
  executeAdminCommand,
  fetchServerApprovals,
  fetchServerAudit,
  fetchServerHealth,
  fetchServerReport,
  runServerPatrol,
  type ServerApproval,
  type ServerAuditEntry,
  type ServerHealth,
} from '../../api/linkin';
import { fetchModuleHealth } from '../../api/modules';
import { activityNavPath } from '../../lib/monitorTabs';

type Busy = 'idle' | 'load' | 'ask' | 'patrol' | 'cmd' | string;

function toneOf(status: string | undefined): string {
  if (status === 'critical' || status === 'failed' || status === 'expired') return 'text-[#FF453A]';
  if (status === 'warn' || status === 'warning' || status === 'pending') return 'text-[#FF9F0A]';
  if (status === 'ok' || status === 'confirmed') return 'text-[#30D158]';
  return 'text-[#AEAEB2]';
}

export default function AdminPanel() {
  const [health, setHealth] = useState<ServerHealth | null>(null);
  const [approvals, setApprovals] = useState<ServerApproval[]>([]);
  const [audit, setAudit] = useState<ServerAuditEntry[]>([]);
  const [report, setReport] = useState('');
  const [moduleHealth, setModuleHealth] = useState<Record<string, unknown> | null>(null);
  const [question, setQuestion] = useState('');
  const [command, setCommand] = useState('time set day');
  const [confirmed, setConfirmed] = useState(false);
  const [answer, setAnswer] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<Busy>('idle');

  const load = useCallback(async () => {
    setBusy('load');
    setError(null);
    try {
      const [snap, pending, logs, catalog] = await Promise.all([
        fetchServerHealth(),
        fetchServerApprovals(false),
        fetchServerAudit(30),
        fetchModuleHealth('minecraft').catch(() => null),
      ]);
      setHealth(snap);
      setApprovals(pending.approvals ?? []);
      setAudit(logs.entries ?? []);
      setModuleHealth(catalog);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (key: Busy, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setMessage(null);
    try {
      await fn();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">Minecraft Admin</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            伺服器運維走具名工具與批准隊列；遊戲指令經 {activityNavPath('minecraft')} 同一套護欄。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={busy !== 'idle'}
          className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8] disabled:opacity-40"
        >
          {busy === 'load' ? '讀取中' : '重新整理'}
        </button>
      </div>

      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}
      {message && <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{message}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[
          { label: '運維狀態', value: health?.status || '—' },
          { label: '乾跑', value: health?.dry_run ? '是' : '否' },
          { label: '待批准', value: String(approvals.length) },
          { label: '世界', value: String((moduleHealth?.world as { name?: string } | undefined)?.name || '—') },
        ].map((card) => (
          <div key={card.label} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2">
            <p className="text-[10px] text-[#8a8f98]">{card.label}</p>
            <p className={`text-sm font-medium ${card.label === '運維狀態' ? toneOf(health?.status) : ''}`}>{card.value}</p>
          </div>
        ))}
      </div>

      <section className="mb-4 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">健康檢查</h3>
        <div className="space-y-1.5">
          {(health?.checks ?? []).length === 0 && <p className="text-[11px] text-[#636366]">尚無檢查結果</p>}
          {(health?.checks ?? []).map((check) => (
            <div key={check.name} className="flex items-start justify-between gap-3 rounded-lg bg-black/20 px-2.5 py-1.5">
              <div>
                <p className="text-[12px] font-medium">{check.name}</p>
                <p className="text-[11px] text-[#8a8f98]">{check.detail || '—'}</p>
              </div>
              <span className={`shrink-0 text-[10px] ${toneOf(check.critical ? 'critical' : check.warning ? 'warn' : check.ok ? 'ok' : 'fail')}`}>
                {check.critical ? 'critical' : check.warning ? 'warn' : check.ok ? 'ok' : 'fail'}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="mb-4 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">運維問答</h3>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="例如：磁盤為什麼漲、哪裡佔空間、巡檢一下"
            className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
          />
          <button
            type="button"
            disabled={busy !== 'idle' || !question.trim()}
            onClick={() =>
              void run('ask', async () => {
                const data = await askServerAdmin(question.trim());
                setAnswer(data);
                setMessage('已送出運維問題');
                await load();
              })
            }
            className="rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40"
          >
            {busy === 'ask' ? '詢問中' : '詢問'}
          </button>
          <button
            type="button"
            disabled={busy !== 'idle'}
            onClick={() =>
              void run('patrol', async () => {
                const data = await runServerPatrol();
                setAnswer(data);
                setMessage('巡檢完成（寫操作仍需批准）');
                await load();
              })
            }
            className="rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[12px] text-[#AEAEB2] disabled:opacity-40"
          >
            {busy === 'patrol' ? '巡檢中' : '巡檢'}
          </button>
        </div>
        {answer && (
          <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-black/30 p-3 text-[11px] leading-relaxed text-[#AEAEB2]">
            {JSON.stringify(answer, null, 2)}
          </pre>
        )}
      </section>

      <section className="mb-4 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">批准隊列（{approvals.length}）</h3>
        {approvals.length === 0 && <p className="py-4 text-center text-xs text-[#636366]">沒有待批准操作</p>}
        <div className="space-y-2">
          {approvals.map((row) => (
            <article key={row.id} className="rounded-lg border border-white/[0.06] bg-black/20 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12px] font-medium">{row.tool}</span>
                <span className={`text-[10px] ${toneOf(row.status)}`}>{row.status}</span>
                <span className="text-[10px] text-[#636366]">{row.id}</span>
              </div>
              {row.question && <p className="mt-1 text-[11px] text-[#AEAEB2]">{row.question}</p>}
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  disabled={busy !== 'idle'}
                  onClick={() =>
                    void run(row.id, async () => {
                      await confirmServerApproval(row.id);
                      setMessage(`已批准 ${row.tool}`);
                      await load();
                    })
                  }
                  className="rounded-lg bg-[#30D158]/15 px-2 py-1 text-[11px] text-[#30D158] disabled:opacity-40"
                >
                  批准
                </button>
                <button
                  type="button"
                  disabled={busy !== 'idle'}
                  onClick={() =>
                    void run(row.id, async () => {
                      await cancelServerApproval(row.id);
                      setMessage(`已取消 ${row.tool}`);
                      await load();
                    })
                  }
                  className="rounded-lg bg-[#FF453A]/15 px-2 py-1 text-[11px] text-[#FF453A] disabled:opacity-40"
                >
                  取消
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="mb-4 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">遊戲指令（Admin.execute）</h3>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
          />
          <label className="flex items-center gap-2 text-[11px] text-[#8a8f98]">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            敏感操作已二次確認
          </label>
          <button
            type="button"
            disabled={busy !== 'idle' || !command.trim()}
            onClick={() =>
              void run('cmd', async () => {
                const data = await executeAdminCommand(command.trim(), confirmed);
                setAnswer(data);
                setMessage(data.executed ? '指令已送出' : '指令未執行');
              })
            }
            className="rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40"
          >
            {busy === 'cmd' ? '執行中' : '執行'}
          </button>
        </div>
      </section>

      <section className="mb-4 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">日報／審計</h3>
          <button
            type="button"
            disabled={busy !== 'idle'}
            onClick={() =>
              void run('load', async () => {
                const data = await fetchServerReport();
                setReport(data.report || '');
              })
            }
            className="text-[11px] text-[#64D2FF] disabled:opacity-40"
          >
            產生日報
          </button>
        </div>
        {report && <pre className="mb-3 max-h-40 overflow-auto rounded-lg bg-black/30 p-3 text-[11px] leading-relaxed text-[#AEAEB2]">{report}</pre>}
        <div className="space-y-1.5">
          {audit.length === 0 && <p className="text-[11px] text-[#636366]">尚無運維審計</p>}
          {audit.slice().reverse().map((row, index) => (
            <div key={`${row.ts}-${index}`} className="rounded-lg bg-black/20 px-2.5 py-1.5 text-[11px] text-[#AEAEB2]">
              <span className="mr-2 text-[#8a8f98]">{String(row.ts || '')}</span>
              <span className="mr-2 font-medium text-[#F5F5F7]">{String(row.tool || 'audit')}</span>
              <span>{String(row.message || row.error || '')}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
