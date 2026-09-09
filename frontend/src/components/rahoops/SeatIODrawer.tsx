/**
 * SeatIODrawer — 右欄單次投遞詳情：輸入（context_sources 分解）／輸出（全文）／上下文。
 */
import { useState } from 'react';
import type { ReactNode } from 'react';
import type { SeatIOFeedRow, SeatIORecord } from '../../types';
import { TIER_LABEL, fmtUsd, fmtWhen } from '../../lib/agentUi';
import { rahoLayerLabel, jumpToRoleDesk } from '../../lib/rahoUi';
import { splitThink } from '../../lib/splitThink';
import MarkdownBody from '../media/MarkdownBody';
import { attemptTag, fmtChars, fmtDuration, seatKindLabel, sourceTone } from './seatModel';

type TabKey = 'input' | 'output' | 'context';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'input', label: '輸入' },
  { key: 'output', label: '輸出' },
  { key: 'context', label: '上下文' },
];

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex min-w-0 items-baseline gap-1.5 py-[2px]">
      <span className="w-[80px] shrink-0 text-[9.5px] tracking-wide text-[var(--apple-tertiary)]">
        {label}
      </span>
      <span className="min-w-0 flex-1 break-words font-mono text-[10.5px] text-[var(--apple-label)]">
        {value}
      </span>
    </div>
  );
}

function CodeBlock({
  title,
  text,
  tone,
  defaultOpen = true,
  maxHeight = '16rem',
}: {
  title: string;
  text: string;
  tone?: string;
  defaultOpen?: boolean;
  maxHeight?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="overflow-hidden rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2 py-1.5 text-left"
      >
        <span className="text-[var(--apple-tertiary)] font-mono text-[9px]">{open ? '▾' : '▸'}</span>
        <span className="text-[10px] font-medium" style={{ color: tone || 'var(--apple-secondary)' }}>
          {title}
        </span>
        <span className="ml-auto font-mono text-[9.5px] text-[var(--apple-tertiary)]">
          {fmtChars(text.length)} 字
        </span>
      </button>
      {open && (
        text ? (
          <pre
            className="whitespace-pre-wrap break-words border-t border-[var(--apple-hairline)] px-2 py-1.5 font-mono text-[10.5px] leading-relaxed text-[var(--apple-label)]"
            style={{ maxHeight, overflowY: 'auto' }}
          >
            {text}
          </pre>
        ) : (
          <p className="border-t border-[var(--apple-hairline)] px-2 py-1.5 text-[10.5px] text-[var(--apple-tertiary)]">
            （空）
          </p>
        )
      )}
    </div>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <h4 className="mb-1 mt-3 first:mt-0 text-[9.5px] font-medium uppercase tracking-wide text-[var(--apple-tertiary)]">
      {children}
    </h4>
  );
}

export default function SeatIODrawer({
  row,
  detail,
  loading,
  error,
  onOpenTask,
  onClose,
}: {
  row: SeatIOFeedRow | null;
  detail: SeatIORecord | null;
  loading: boolean;
  error: string | null;
  onOpenTask: (taskId: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<TabKey>('input');
  const [richOutput, setRichOutput] = useState(true);

  if (!row) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-1.5 px-5 py-10 text-center">
        <p className="text-[11.5px] text-[var(--apple-secondary)]">選擇左側任一投遞記錄</p>
        <p className="text-[10.5px] leading-relaxed text-[var(--apple-tertiary)]">
          這裡會顯示該席位實際餵給模型的系統提示詞、組裝後的 prompt 全文，以及模型回傳的內容與上下文來源分解。
        </p>
      </div>
    );
  }

  const rec = detail; // 全文僅在 detail 到位後可讀
  const ioId = row.io_id;
  const sources = rec?.context_sources ?? [];
  const totalSourceChars = sources.reduce((sum, s) => sum + (Number(s.chars) || 0), 0);
  const tools = rec?.allowed_tools ?? row.allowed_tools ?? [];
  const inputRef = rec?.input_ref ?? row.input_ref;
  const taskKind = tab === 'output' && rec ? splitThink(rec.response || '') : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 抽屉標題 */}
      <div className="shrink-0 border-b border-[var(--apple-hairline)] px-2.5 py-2">
        <div className="flex min-w-0 items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate text-[12px] font-semibold text-[var(--apple-label)]">
              {row.role_label || row.role}
            </p>
            <p className="mt-[2px] truncate text-[10px] text-[var(--apple-secondary)]">
              {row.layer_label || rahoLayerLabel(row.layer)} · {seatKindLabel(row.kind)} ·{' '}
              {row.title || row.item_id || '—'}
            </p>
            <p className="mt-[3px] truncate font-mono text-[9.5px] text-[var(--apple-tertiary)]" title={ioId}>
              {ioId}
              {attemptTag(row) ? ` · ${attemptTag(row)}` : ''}
              {` · ${fmtWhen(row.ts)}`}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="關閉詳情"
            className="shrink-0 rounded-[6px] border border-[var(--apple-hairline)] px-1.5 py-[2px] font-mono text-[10px] text-[var(--apple-secondary)] hover:bg-[var(--apple-surface)] hover:text-[var(--apple-label)]"
          >
            ✕
          </button>
        </div>
      </div>

      {/* tabs */}
      <div className="flex shrink-0 gap-1 border-b border-[var(--apple-hairline)] px-2 py-1.5">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-[6px] px-2 py-[3px] text-[10.5px] transition-colors ${
              tab === t.key
                ? 'bg-[var(--apple-blue)]/18 text-[var(--apple-label)]'
                : 'text-[var(--apple-secondary)] hover:bg-[var(--apple-surface)]'
            }`}
          >
            {t.label}
          </button>
        ))}
        <span className="ml-auto self-center font-mono text-[9.5px] text-[var(--apple-tertiary)]">
          {fmtChars(row.prompt_length)}→{fmtChars(row.response_length)} 字
        </span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2.5 py-2">
        {error && (
          <p
            className="mb-2 rounded-[8px] border px-2 py-1.5 text-[10.5px]"
            style={{ borderColor: 'rgba(255,69,58,.35)', background: 'rgba(255,69,58,.1)', color: 'var(--apple-red)' }}
          >
            {error}
          </p>
        )}
        {!rec ? (
          loading ? (
            <p className="py-6 text-center text-[11px] text-[var(--apple-secondary)]">載入全文中…</p>
          ) : (
            <p className="py-6 text-center text-[11px] text-[var(--apple-secondary)]">
              全文尚未取得，可稍後重試或於下方查看列表層級欄位。
            </p>
          )
        ) : (
          <>
            {tab === 'input' && (
              <div>
                <SectionTitle>上下文來源分解（{sources.length} 塊 · {fmtChars(totalSourceChars)} 字）</SectionTitle>
                {sources.length === 0 ? (
                  <p className="rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-2 text-[10.5px] leading-relaxed text-[var(--apple-secondary)]">
                    此投遞未記錄來源分解（例如早期軌跡或非執行類投遞）。下方 prompt 全文仍為實際餵給模型的內容。
                  </p>
                ) : (
                  <ol className="flex flex-col gap-[5px]">
                    {sources.map((src, idx) => (
                      <li
                        key={`${src.kind}-${idx}`}
                        className="rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-1.5"
                        style={{ borderLeft: `2px solid ${sourceTone(src.kind)}` }}
                      >
                        <div className="flex min-w-0 items-baseline gap-1.5">
                          <span className="shrink-0 font-mono text-[9px] text-[var(--apple-tertiary)]">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-[var(--apple-label)]">
                            {src.label || src.kind}
                          </span>
                          <span className="shrink-0 font-mono text-[9.5px] text-[var(--apple-secondary)]">
                            {fmtChars(src.chars)} 字
                          </span>
                        </div>
                        <p className="mt-[2px] line-clamp-2 font-mono text-[9.5px] leading-relaxed text-[var(--apple-tertiary)]">
                          {src.preview || '（空）'}
                        </p>
                        <p className="mt-[1px] font-mono text-[9px] uppercase text-[var(--apple-tertiary)]">
                          {src.kind}
                        </p>
                      </li>
                    ))}
                  </ol>
                )}

                <SectionTitle>模型實際收到的文字</SectionTitle>
                <div className="flex flex-col gap-1.5">
                  <CodeBlock title="system（系統提示詞全文）" text={rec.system} tone="var(--apple-gray)" defaultOpen={false} />
                  <CodeBlock
                    title="prompt（組裝後的投遞全文）"
                    text={rec.prompt}
                    tone="var(--apple-blue)"
                    maxHeight="26rem"
                  />
                </div>

                <SectionTitle>投遞參數</SectionTitle>
                <div className="rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-1.5">
                  <Field
                    label="tier"
                    value={`${rec.tier || '—'}${TIER_LABEL[rec.tier] ? `（${TIER_LABEL[rec.tier]}）` : ''}`}
                  />
                  <Field label="temperature" value={rec.temperature ?? '—'} />
                  <Field label="model" value={rec.model || '—'} />
                  <Field
                    label="工具白名單"
                    value={
                      tools.length ? (
                        <span className="flex flex-wrap gap-1">
                          {tools.map((t) => (
                            <span
                              key={t}
                              className="rounded-[4px] bg-[var(--apple-blue)]/12 px-1 py-[1px] text-[9.5px] text-[var(--apple-label)]"
                            >
                              {t}
                            </span>
                          ))}
                        </span>
                      ) : (
                        '—'
                      )
                    }
                  />
                  <Field
                    label="input_ref"
                    value={Array.isArray(inputRef) ? inputRef.join('、') : inputRef || '—'}
                  />
                  <Field label="output_schema" value={rec.output_schema || '—'} />
                  <Field label="success_criteria" value={rec.success_criteria || '—'} />
                </div>
              </div>
            )}

            {tab === 'output' && (
              <div>
                {rec.truncated && (
                  <p
                    className="mb-2 rounded-[8px] border px-2 py-1.5 text-[10.5px]"
                    style={{
                      borderColor: 'rgba(255,159,10,.35)',
                      background: 'rgba(255,159,10,.1)',
                      color: 'var(--apple-orange)',
                    }}
                  >
                    正文已被後端截斷（記錄長度 {fmtChars(rec.response_length)} 字），非模型完整輸出。
                  </p>
                )}
                {taskKind?.thinking && (
                  <>
                    <SectionTitle>thinking（思考過程）</SectionTitle>
                    <pre className="mb-2 max-h-56 overflow-y-auto whitespace-pre-wrap break-words rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-1.5 font-mono text-[10.5px] leading-relaxed text-[var(--apple-secondary)]">
                      {taskKind.thinking}
                    </pre>
                  </>
                )}
                <div className="mb-1.5 flex items-center gap-1">
                  <span className="mr-auto text-[9.5px] uppercase tracking-wide text-[var(--apple-tertiary)]">
                    response（模型回傳全文 · {fmtChars(rec.response_length)} 字）
                  </span>
                  <button
                    type="button"
                    onClick={() => setRichOutput((v) => !v)}
                    className="rounded-[6px] border border-[var(--apple-hairline)] px-1.5 py-[2px] font-mono text-[9.5px] text-[var(--apple-secondary)] hover:bg-[var(--apple-surface)]"
                  >
                    {richOutput ? 'Markdown' : '原文'}
                  </button>
                </div>
                {rec.response ? (
                  richOutput ? (
                    <div className="rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2.5 py-2 text-[11.5px]">
                      <MarkdownBody markdown={taskKind?.content || rec.response} />
                    </div>
                  ) : (
                    <pre className="max-h-[34rem] overflow-y-auto whitespace-pre-wrap break-words rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-1.5 font-mono text-[10.5px] leading-relaxed text-[var(--apple-label)]">
                      {rec.response}
                    </pre>
                  )
                ) : (
                  <p className="rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-2 text-[10.5px] text-[var(--apple-secondary)]">
                    （無回應內容）
                  </p>
                )}
              </div>
            )}

            {tab === 'context' && (
              <div>
                <div className="rounded-[8px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] px-2 py-1.5">
                  <Field label="run_id" value={rec.run_id || '—'} />
                  <Field label="task_id" value={rec.task_id || '—'} />
                  <Field label="item_id" value={rec.item_id || '—'} />
                  <Field
                    label="attempt"
                    value={`${rec.attempt || 0} · step ${rec.step || 0} · tool_steps ${rec.tool_steps || 0}`}
                  />
                  <Field label="final" value={rec.final ? '是（最終產出）' : '否'} />
                  <Field label="model" value={rec.model || '—'} />
                  <Field label="tier" value={rec.tier || '—'} />
                  <Field label="時間" value={fmtWhen(rec.ts)} />
                  <Field label="耗時" value={fmtDuration(rec.duration_ms)} />
                  <Field label="花費" value={rec.cost_usd ? fmtUsd(rec.cost_usd) : '$0'} />
                  <Field label="降級" value={rec.degraded ? '是' : '否'} />
                  <Field label="io_id" value={rec.io_id} />
                </div>
                {rec.error && (
                  <pre
                    className="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap break-words rounded-[8px] border px-2 py-1.5 font-mono text-[10.5px] leading-relaxed"
                    style={{
                      borderColor: 'rgba(255,69,58,.35)',
                      background: 'rgba(255,69,58,.08)',
                      color: 'var(--apple-red)',
                    }}
                  >
                    {rec.error}
                  </pre>
                )}
                <div className="mt-3 flex flex-col gap-1.5">
                  <button
                    type="button"
                    disabled={!rec.task_id}
                    onClick={() => rec.task_id && onOpenTask(rec.task_id)}
                    className="rounded-[8px] border border-[var(--apple-blue)]/50 bg-[var(--apple-blue)]/12 px-2 py-1.5 text-[11px] text-[var(--apple-label)] hover:bg-[var(--apple-blue)]/25 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    打開此任務
                  </button>
                  <button
                    type="button"
                    disabled={!rec.role || rec.role === 'user' || rec.role === 'environment_kernel'}
                    onClick={() => jumpToRoleDesk(rec.role)}
                    className="rounded-[8px] border border-[var(--apple-hairline)] px-2 py-1.5 text-[11px] text-[var(--apple-secondary)] hover:bg-[var(--apple-surface)] hover:text-[var(--apple-label)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    打開此席位工作台
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
