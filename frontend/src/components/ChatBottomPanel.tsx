/**
 * 對話工作台底部：產出文件 / 終端 / 問題。
 */
import type { WsFile, WsProblem, WsTermLine } from '../lib/chatWorkspace';
import { langOf, tokenizeCode, wsTreeRows } from '../lib/chatWorkspace';

export type BottomTab = 'files' | 'terminal' | 'problems';

interface ChatBottomPanelProps {
  collapsed: boolean;
  onToggle: () => void;
  tab: BottomTab;
  onTab: (tab: BottomTab) => void;
  files: WsFile[];
  fileId: string | null;
  onFile: (id: string) => void;
  terminal: WsTermLine[];
  problems: WsProblem[];
  onProblem?: (id: string) => void;
}

export function WsCodePreview({ file }: { file: WsFile | null }) {
  if (!file) {
    return <div className="ws-code"><div className="ws-code-h"><span>選擇檔案以預覽</span></div></div>;
  }
  const lines = (file.content || ' ').split('\n');
  return (
    <div className="ws-code">
      <div className="ws-code-h">
        <span>{file.path}</span>
        <span>{langOf(file.path)}</span>
      </div>
      {lines.map((line, i) => (
        <div key={`${file.id}-${i}`} className={`ws-code-line${line.trimStart().startsWith('+') ? ' is-add' : ''}`}>
          <span className="ws-ln">{i + 1}</span>
          <span className="ws-lc">
            {tokenizeCode(line).map((tok, j) => {
              const cls =
                tok.k === 'keyword'
                  ? 'kw'
                  : tok.k === 'function'
                    ? 'fn'
                    : tok.k === 'string'
                      ? 'str'
                      : tok.k === 'comment'
                        ? 'cmt'
                        : tok.k === 'variable'
                          ? 'var'
                          : tok.k === 'number'
                            ? 'num'
                            : '';
              return cls ? (
                <span key={j} className={cls}>
                  {tok.t}
                </span>
              ) : (
                <span key={j}>{tok.t}</span>
              );
            })}
          </span>
        </div>
      ))}
    </div>
  );
}

function Ico({ d }: { d: string }) {
  return (
    <svg className="ws-ico ws-ico-sm" viewBox="0 0 24 24" aria-hidden>
      <path d={d} />
    </svg>
  );
}

export default function ChatBottomPanel({
  collapsed,
  onToggle,
  tab,
  onTab,
  files,
  fileId,
  onFile,
  terminal,
  problems,
  onProblem,
}: ChatBottomPanelProps) {
  const active = files.find((f) => f.id === fileId) ?? files[0] ?? null;
  const tree = wsTreeRows(files);

  return (
    <div className={`ws-bottom${collapsed ? ' is-off' : ''}`}>
      <div className="ws-bottom-h">
        <div className="ws-tabs">
          <button type="button" className={`ws-tab${tab === 'files' ? ' is-on' : ''}`} onClick={() => onTab('files')}>
            <Ico d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            AI 輸出文件空間 <span className="ws-count">{files.length}</span>
          </button>
          <button type="button" className={`ws-tab${tab === 'terminal' ? ' is-on' : ''}`} onClick={() => onTab('terminal')}>
            <Ico d="M4 17l6-6-6-6M12 19h8" />
            終端機 <span className="ws-count">{terminal.length}</span>
          </button>
          <button type="button" className={`ws-tab${tab === 'problems' ? ' is-on' : ''}`} onClick={() => onTab('problems')}>
            <Ico d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            問題{' '}
            <span className={`ws-count${problems.length ? ' is-err' : ''}`}>{problems.length}</span>
          </button>
        </div>
        <button type="button" className="ws-btn ws-btn-icon" onClick={onToggle} aria-label={collapsed ? '展開底部面板' : '收合底部面板'}>
          <Ico d="M6 18L18 6M6 6l12 12" />
        </button>
      </div>
      <div className="ws-bottom-body">
        {tab === 'files' && (
          <>
            <div className="ws-tree">
              {tree.length === 0 && <p className="ws-empty">尚無產出檔</p>}
              {tree.map((row) =>
                row.kind === 'dir' ? (
                  <div
                    key={`d-${row.path}`}
                    className="ws-tree-i is-dir"
                    style={{ paddingLeft: 12 + row.depth * 16 }}
                  >
                    {row.name}
                  </div>
                ) : (
                  <button
                    key={row.file!.id}
                    type="button"
                    className={`ws-tree-i${active?.id === row.file!.id ? ' is-on' : ''}`}
                    style={{ paddingLeft: 12 + row.depth * 16 }}
                    onClick={() => onFile(row.file!.id)}
                  >
                    {row.name}
                    {row.file?.size && <span className="ws-tree-meta">{row.file.size}</span>}
                    <span className={`ws-st ${row.file?.status === 'added' ? 'A' : 'M'}`}>
                      {row.file?.status === 'added' ? 'A' : 'M'}
                    </span>
                  </button>
                ),
              )}
            </div>
            <WsCodePreview file={active} />
          </>
        )}
        {tab === 'terminal' && (
          <div className="ws-preview ws-term">
            {terminal.length === 0 ? (
              <span className="info">等待任務事件…</span>
            ) : (
              terminal.map((line, i) => (
                <div key={`${i}-${line.text.slice(0, 24)}`} className={`ws-term-line ${line.kind}`}>
                  {line.text}
                </div>
              ))
            )}
          </div>
        )}
        {tab === 'problems' && (
          <div className="ws-preview" style={{ background: 'var(--ws-panel)' }}>
            {problems.length === 0 && <p className="ws-empty">沒有問題</p>}
            {problems.map((p) => (
              <button
                key={p.id}
                type="button"
                className={`ws-problem${p.tone === 'warn' ? ' is-warn' : ' is-err'}`}
                onClick={() => onProblem?.(p.id)}
                style={{ width: 'calc(100% - 32px)', textAlign: 'left', cursor: onProblem ? 'pointer' : 'default' }}
              >
                <div>
                  <b>{p.title}</b>
                  {p.loc && <span>{p.loc}</span>}
                  <span>{p.detail}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
