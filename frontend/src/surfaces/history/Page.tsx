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

const primaryButton = 'reflect-action';

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
      className="reflect-page h-full overflow-y-auto [scrollbar-color:var(--console-line-strong)_transparent]"
    >
      <div className="reflect-history">
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
      <h1 className="reflect-title">歷史對話記錄</h1>
      <p className="reflect-lead">選擇一筆，在對話裡繼續。</p>
      {rows.length === 0 ? (
        <div className="reflect-block">
          <p>還沒有對話。</p>
          <a href={CONVERSATION_HASH} className={primaryButton}>
            前往對話
          </a>
        </div>
      ) : (
        <ul>
          {rows.map((row) => (
            <li key={row.id}>
              <button type="button" onClick={() => onOpen(row.id)} className="reflect-row">
                <span className="reflect-row__title">{row.title}</span>
                <span className="reflect-row__when">{row.when}</span>
                <span className="reflect-row__preview">{row.preview}</span>
                <span className="reflect-row__meta">
                  {row.messageCount} 則
                  {row.active ? <span className="reflect-row__live">作用中</span> : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="reflect-note">本機儲存</p>
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
      <button type="button" onClick={onBack} className="reflect-back">
        返回
      </button>
      <h1 className="reflect-title break-words">{record.title}</h1>
      <p className="reflect-note">
        {record.when}
        <span className="reflect-row__live">{record.messageCount} 則</span>
        {record.active ? <span className="reflect-row__live">作用中</span> : null}
      </p>
      <button
        type="button"
        onClick={() => {
          if (!handOff(record.id)) onMissing();
        }}
        className={primaryButton}
      >
        繼續
      </button>
      {record.turns.length === 0 ? (
        <p className="reflect-note">這段對話還沒有內容。</p>
      ) : (
        <ol className="reflect-block">
          {record.turns.map((turn) => (
            <li key={turn.id} className="mt-5">
              <span className="flex items-baseline justify-between gap-4">
                <span className={turn.role === 'user' ? 'reflect-row__title' : 'reflect-note'}>{turn.label}</span>
                <span className="reflect-row__when">{turn.when}</span>
              </span>
              <p className="whitespace-pre-wrap break-words">{turn.content}</p>
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
      <h1 className="reflect-title">找不到這段對話</h1>
      <p className="reflect-lead">這筆記錄已不在本機的對話裡。</p>
      <button type="button" onClick={onBack} className={primaryButton}>
        返回列表
      </button>
    </>
  );
}
