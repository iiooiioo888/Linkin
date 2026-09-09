/**
 * 右側節點工作台：思考過程 / 對話 / 產出文件。
 */
import type { ReactNode } from 'react';
import { eventClock } from '../lib/taskTiming';
import type { WsFile, WsThinkingStep } from '../lib/chatWorkspace';
import { WsCodePreview } from './ChatBottomPanel';

export type DrawerTab = 'thinking' | 'chat' | 'files';

interface ChatNodeDrawerProps {
  open: boolean;
  nodeId: string;
  title: string;
  tab: DrawerTab;
  onTab: (tab: DrawerTab) => void;
  onClose: () => void;
  thinking: WsThinkingStep[];
  files: WsFile[];
  fileId: string | null;
  onFile: (id: string) => void;
  chatCount: number;
  chat: ReactNode;
  composer: ReactNode;
  decision?: ReactNode;
  onAccept?: () => void;
}

function Ico({ d }: { d: string }) {
  return (
    <svg className="ws-ico ws-ico-sm" viewBox="0 0 24 24" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export default function ChatNodeDrawer({
  open,
  nodeId,
  title,
  tab,
  onTab,
  onClose,
  thinking,
  files,
  fileId,
  onFile,
  chatCount,
  chat,
  composer,
  decision,
  onAccept,
}: ChatNodeDrawerProps) {
  const active = files.find((f) => f.id === fileId) ?? files[0] ?? null;

  return (
    <aside className={`ws-drawer${open ? ' is-on' : ''}`} aria-label="節點工作台">
      <div className="ws-drawer-h">
        <div>
          <div className="ws-drawer-id">{nodeId}</div>
          <div className="ws-drawer-t">{title}</div>
        </div>
        <button type="button" className="ws-btn ws-btn-icon" onClick={onClose} aria-label="關閉抽屜">
          <Ico d="M6 18L18 6M6 6l12 12" />
        </button>
      </div>

      {decision}

      <div className="ws-drawer-tabs">
        <button type="button" className={`ws-d-tab${tab === 'thinking' ? ' is-on' : ''}`} onClick={() => onTab('thinking')}>
          <Ico d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          思考過程
        </button>
        <button type="button" className={`ws-d-tab${tab === 'chat' ? ' is-on' : ''}`} onClick={() => onTab('chat')}>
          <Ico d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          對話 {chatCount > 0 && <span className="ws-count">{chatCount}</span>}
        </button>
        <button type="button" className={`ws-d-tab${tab === 'files' ? ' is-on' : ''}`} onClick={() => onTab('files')}>
          <Ico d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          產出文件 {files.length > 0 && <span className="ws-count">{files.length}</span>}
        </button>
      </div>

      <div className="ws-drawer-body">
        {tab === 'thinking' && (
          <div className="ws-think">
            {thinking.length === 0 && <p className="ws-empty">尚無思考紀錄。送出任務後會顯示在這裡。</p>}
            {thinking.map((step, i) => (
              <div
                key={step.id}
                className={`ws-t-item${step.kind === 'success' ? ' is-ok' : step.kind === 'process' ? ' is-run' : ' is-warn'}`}
              >
                <div className="ws-t-line">
                  <div className="ws-t-dot" />
                  {i < thinking.length - 1 && <div className="ws-t-conn" />}
                </div>
                <div className="ws-t-content">
                  <div className="ws-t-time">
                    <span>{eventClock(step.ts)}</span>
                    {step.tokens != null && <span className="ws-t-tok">{step.tokens} tokens</span>}
                  </div>
                  <div className="ws-t-text">
                    <strong>{step.title}</strong>
                    {step.text ? `\n${step.text}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'chat' && (
          <div className="ws-chat">
            {chat}
            {composer}
          </div>
        )}

        {tab === 'files' && (
          <>
            <div className="ws-df-list">
              {files.length === 0 && <p className="ws-empty">此節點尚無產出檔</p>}
              {files.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`ws-df${active?.id === f.id ? ' is-on' : ''}`}
                  onClick={() => onFile(f.id)}
                >
                  <span className="ws-df-name">{f.path}</span>
                  <span className={`ws-df-st ${f.status === 'added' ? 'A' : 'M'}`}>
                    {f.status === 'added' ? 'Added' : 'Modified'}
                  </span>
                </button>
              ))}
            </div>
            <div className="ws-df-preview">
              <WsCodePreview file={active} />
            </div>
            <div className="ws-df-acts">
              <button type="button" className="ws-btn" onClick={() => active && onFile(active.id)}>
                <Ico d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                預覽
              </button>
              <button
                type="button"
                className="ws-btn ws-btn-primary ws-btn-full"
                disabled={!files.length}
                onClick={onAccept}
              >
                <Ico d="M5 13l4 4L19 7" />
                接受所有變更 ({files.length})
              </button>
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
