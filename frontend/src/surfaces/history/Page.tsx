import { useEffect, useMemo, useState } from 'react';
import {
  browserSessionStore,
  CONVERSATION_HASH,
  listHistory,
  openHistory,
  resumeHistory,
  type HistoryRow,
  type OpenedHistory,
} from './model';

const focusRing =
  'focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:[outline-color:var(--console-accent)]!';

const primaryButton = `self-start inline-flex min-h-11 items-center rounded-[10px] bg-[var(--console-accent)] px-3.5 text-[12px] font-medium text-[var(--console-accent-ink)] ${focusRing}`;

/**
 * 既有對話頁的 useChatSessions 只在掛載時讀取作用中會話。
 * 寫入後重新載入，對話才會從這一筆繼續。
 */
function handOff(id: string) {
  const next = resumeHistory(browserSessionStore, id);
  if (!next) return false;
  window.location.hash = next.hash;
  window.location.reload();
  return true;
}

export function HistoryPage() {
  const [openedId, setOpenedId] = useState<string | null>(null);
  const [lost, setLost] = useState(false);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const bump = () => setVersion((value) => value + 1);
    window.addEventListener('storage', bump);
    window.addEventListener('focus', bump);
    return () => {
      window.removeEventListener('storage', bump);
      window.removeEventListener('focus', bump);
    };
  }, []);

  const rows = useMemo(() => listHistory(browserSessionStore), [version]);
  const opened = useMemo(
    () => (openedId ? openHistory(browserSessionStore, openedId) : null),
    [openedId, version],
  );

  return (
    <div
      data-surface="history"
      className="h-full overflow-y-auto bg-[var(--console-bg)] text-[var(--console-ink)] [scrollbar-color:var(--console-line-strong)_transparent]"
    >
      <div className="mx-auto flex w-full max-w-[72ch] flex-col px-[var(--u3)] py-[var(--u4)] sm:px-[var(--u4)]">
        {openedId && (lost || !opened) ? (
          <MissingRecord
            onBack={() => {
              setLost(false);
              setOpenedId(null);
            }}
          />
        ) : opened ? (
          <Transcript
            record={opened}
            onBack={() => setOpenedId(null)}
            onMissing={() => setLost(true)}
          />
        ) : (
          <HistoryList rows={rows} onOpen={setOpenedId} />
        )}
      </div>
    </div>
  );
}

function HistoryList({ rows, onOpen }: { rows: HistoryRow[]; onOpen: (id: string) => void }) {
  return (
    <>
      <h1 className="text-[22px] font-semibold leading-[1.25] tracking-[-0.02em]">歷史對話記錄</h1>
      <p className="mt-2 text-[13px] leading-normal text-[var(--console-sub)]">選擇一筆，在對話裡繼續。</p>
      {rows.length === 0 ? (
        <div className="mt-[var(--u6)]">
          <p className="text-[15px] font-semibold leading-snug">還沒有對話。</p>
          <a
            href={CONVERSATION_HASH}
            className={`mt-[var(--u3)] ${primaryButton}`}
          >
            前往對話
          </a>
        </div>
      ) : (
        <ul className="mt-[var(--u4)] flex flex-col">
          {rows.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                onClick={() => onOpen(row.id)}
                className={`w-full rounded-[10px] px-3 py-3 text-left transition-colors duration-150 hover:bg-[var(--console-card)] motion-reduce:transition-none ${focusRing}`}
              >
                <span className="flex items-baseline justify-between gap-4">
                  <span className="truncate text-[15px] font-semibold leading-snug">{row.title}</span>
                  <span className="shrink-0 text-[12px] text-[var(--console-sub)]">{row.when}</span>
                </span>
                <span className="mt-1 block truncate text-[13px] leading-normal text-[var(--console-sub)]">
                  {row.preview}
                </span>
                <span className="mt-1 block text-[12px] text-[var(--console-sub)]">
                  {row.messageCount} 則
                  {row.active ? <span className="text-[var(--console-accent)]"> · 作用中</span> : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-[var(--u4)] text-[12px] text-[var(--console-sub)]">本機儲存</p>
    </>
  );
}

function Transcript({
  record,
  onBack,
  onMissing,
}: {
  record: OpenedHistory;
  onBack: () => void;
  onMissing: () => void;
}) {
  return (
    <>
      <button
        type="button"
        onClick={onBack}
        className={`w-fit rounded-[6px] px-1 py-1 text-[12px] text-[var(--console-sub)] hover:text-[var(--console-ink)] ${focusRing}`}
      >
        返回
      </button>
      <h1 className="mt-3 text-[22px] font-semibold leading-[1.25] tracking-[-0.02em] break-words">
        {record.title}
      </h1>
      <p className="mt-2 text-[12px] text-[var(--console-sub)]">
        {record.when} · {record.messageCount} 則
        {record.active ? <span className="text-[var(--console-accent)]"> · 作用中</span> : null}
      </p>
      <button
        type="button"
        onClick={() => {
          if (!handOff(record.id)) onMissing();
        }}
        className={`mt-[var(--u3)] ${primaryButton}`}
      >
        繼續
      </button>
      {record.turns.length === 0 ? (
        <p className="mt-[var(--u4)] text-[13px] leading-normal text-[var(--console-sub)]">這段對話還沒有內容。</p>
      ) : (
        <ol className="mt-[var(--u4)] flex flex-col gap-[var(--u3)]">
          {record.turns.map((turn) => (
            <li key={turn.id} className="flex flex-col gap-1">
              <span className="flex items-baseline justify-between gap-4 text-[12px]">
                <span className={turn.role === 'user' ? 'font-semibold text-[var(--console-ink)]' : 'text-[var(--console-sub)]'}>
                  {turn.label}
                </span>
                <span className="shrink-0 text-[var(--console-sub)]">{turn.when}</span>
              </span>
              <p className="whitespace-pre-wrap break-words text-[13px] leading-normal">{turn.content}</p>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

function MissingRecord({ onBack }: { onBack: () => void }) {
  return (
    <>
      <h1 className="text-[22px] font-semibold leading-[1.25] tracking-[-0.02em]">找不到這段對話</h1>
      <p className="mt-2 text-[13px] leading-normal text-[var(--console-sub)]">這筆記錄已不在本機的對話裡。</p>
      <button
        type="button"
        onClick={onBack}
        className={`mt-[var(--u3)] ${primaryButton}`}
      >
        返回列表
      </button>
    </>
  );
}
