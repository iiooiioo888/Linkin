/**
 * ChatView — 對話工作台（1.html 風格：看板 + 抽屜對話 + 底部檔案）。
 */
import { useEffect, useMemo, useState } from 'react';
import type { ChatMessage } from '../types';
import { cancelTask, resumeTask } from '../api/client';
import InputBar from './InputBar';
import type { SendOptions } from './InputBar';
import MessageList from './MessageList';
import ErrorState from './ui/ErrorState';
import RahoDecisionBar from './RahoDecisionBar';
import ChatNodeDrawer from './ChatNodeDrawer';
import type { DrawerTab } from './ChatNodeDrawer';
import ChatBottomPanel from './ChatBottomPanel';
import type { BottomTab } from './ChatBottomPanel';
import { L0BiasHint } from './L0BiasHint';
import { COMPANY_PHASES, OPC_PHASES, STANDARD_PHASES, ITEM_STATUS_META, elapsed, roleLabel } from './TaskPanel';
import {
  avatarColor,
  avatarInitial,
  flattenWsNodes,
  nodeCode,
  numBudget,
  WS_KANBAN_COLUMNS,
  wsFiles,
  wsProblems,
  wsTerminal,
  wsThinking,
  wsTokens,
} from '../lib/chatWorkspace';
import { formatDurationCompact, taskEta, useNowTick } from '../lib/taskTiming';

interface ChatViewProps {
  messages: ChatMessage[];
  sessionId: string;
  loading: boolean;
  sending: boolean;
  error: string | null;
  lastQuery: string | null;
  llmConfigured?: boolean | null;
  onOpenSettings?: () => void;
  onSend: (text: string, options: SendOptions) => void;
  onRetry: () => void;
  onDismissError: () => void;
  onOpenTask: (messageId: string) => void;
  onOpenTrace?: (taskId: string) => void;
  onSuggest: (text: string, company: boolean) => void;
  onGrillAnswer?: (messageId: string, answer: string, forceLock?: boolean) => void;
  onBattlePick?: (messageId: string, choice: string) => void;
  onDecisionPending?: (hasPending: boolean) => void;
  onDecisionResolved?: (decisionId?: string) => void;
}

function activeTaskMessage(messages: ChatMessage[]) {
  return (
    [...messages].reverse().find(
      (m) =>
        m.streaming ||
        m.taskState?.status === 'running' ||
        m.taskState?.status === 'pending' ||
        (m.taskState?.raho?.pending_decisions?.length ?? 0) > 0,
    ) ?? null
  );
}

function nodeElapsed(createdAt: string | undefined, updatedAt: string | undefined, now: number, live: boolean): string {
  const start = Date.parse(createdAt || updatedAt || '');
  if (!Number.isFinite(start)) return '';
  const end = live ? now : Date.parse(updatedAt || '') || now;
  const sec = Math.max(0, (end - start) / 1000);
  if (sec < 1) return live ? '0s' : '';
  return formatDurationCompact(sec);
}

function statusMeta(status: string, pending: boolean): { label: string; cls: string } {
  if (pending) return { label: '等待裁決', cls: 'is-run' };
  if (status === 'running' || status === 'pending') return { label: '執行中', cls: 'is-run' };
  if (status === 'completed') return { label: '已完成', cls: 'is-ok' };
  if (status === 'failed' || status === 'cancelled') return { label: status === 'failed' ? '失敗' : '已暫停', cls: 'is-err' };
  return { label: '待命', cls: 'is-idle' };
}

export default function ChatView({
  messages,
  sessionId,
  loading,
  sending,
  error,
  lastQuery,
  llmConfigured,
  onOpenSettings,
  onSend,
  onRetry,
  onDismissError,
  onOpenTask,
  onOpenTrace,
  onSuggest,
  onGrillAnswer,
  onBattlePick,
  onDecisionPending,
  onDecisionResolved,
}: ChatViewProps) {
  const live = activeTaskMessage(messages) ?? messages.filter((m) => m.taskState).at(-1) ?? null;
  const task = live?.taskState ?? null;
  const pending = task?.raho?.pending_decisions ?? [];
  const hasPending = pending.some((p) => !p.resolved && (p.choices?.length ?? 0) > 0);
  const grilling = messages.some((m) => Boolean(m.grill && !m.grill.locked && !m.grill.terminated));
  const waitingBattle = messages.some(
    (m) => m.battle?.status === 'ESCALATE_TO_USER' && m.battle.waiting_for_user_decision,
  );

  const [drawerOpen, setDrawerOpen] = useState(true);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>('chat');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [bottomTab, setBottomTab] = useState<BottomTab>('files');
  const [bottomOff, setBottomOff] = useState(false);
  const [fileId, setFileId] = useState<string | null>(null);
  const [actError, setActError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!hasPending) return;
    setDrawerOpen(true);
    setDrawerTab('thinking');
  }, [hasPending]);

  const running = task?.status === 'running' || task?.status === 'pending';
  const now = useNowTick(Boolean(running));
  const eta = task ? taskEta(task, now) : null;
  const nodes = useMemo(() => flattenWsNodes(task), [task]);
  const selected = nodes.find((n) => n.item.id === selectedId) ?? null;
  const files = useMemo(() => wsFiles(task, nodes), [task, nodes]);
  const nodeFiles = selected ? files.filter((f) => !f.itemId || f.itemId === selected.item.id) : files;
  const thinking = useMemo(
    () => wsThinking(task, live?.thinking ?? '', pending),
    [task, live?.thinking, pending],
  );
  const terminal = useMemo(() => wsTerminal(task), [task]);
  const problems = useMemo(() => wsProblems(task, pending, nodes), [task, pending, nodes]);

  const query = task?.query || lastQuery || messages.find((m) => m.role === 'user')?.content || '新對話';
  const title = query.replace(/\s+/g, ' ').slice(0, 64);
  const phases = task?.resolved_path === 'opc' ? OPC_PHASES : task?.resolved_path === 'company' ? COMPANY_PHASES : STANDARD_PHASES;
  const phaseLabel = phases.find((p) => p.key === task?.phase)?.label ?? (task?.phase || '待命');
  const pill = statusMeta(task?.status ?? '', hasPending);
  const spent = numBudget(task, 'task_spent');
  const limit = numBudget(task, 'task_limit') || 2;
  const tokens = wsTokens(task);
  const model = String(task?.budget?.active_tier || '').trim();
  const doneN = nodes.filter((n) => n.status === 'done').length;
  const totalN = nodes.length;
  const successPct = totalN ? Math.round((doneN / totalN) * 100) : running ? 0 : 100;
  const failN = nodes.filter((n) => n.status === 'blocked').length;

  const handlePause = async () => {
    if (!task) return;
    setActError(null);
    try {
      await cancelTask(task.task_id);
    } catch (err) {
      setActError((err as Error).message);
    }
  };

  const handleResume = async () => {
    if (!task) return;
    setActError(null);
    try {
      await resumeTask(task.task_id);
    } catch (err) {
      setActError((err as Error).message);
    }
  };

  return (
    <div className="ws">
      <div className="ws-main">
        <nav className="ws-nav">
          <div className="ws-crumb">
            靈境 · 任務監控 / <strong>{title}</strong>
          </div>
          <div className="ws-nav-acts">
            {onOpenSettings && (
              <button type="button" className="ws-btn ws-btn-icon" onClick={onOpenSettings} aria-label="設定">
                ⚙
              </button>
            )}
            {running && (
              <button type="button" className="ws-btn ws-btn-danger" onClick={() => void handlePause()}>
                <svg className="ws-ico ws-ico-sm" viewBox="0 0 24 24" aria-hidden>
                  <path d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                暫停
              </button>
            )}
            {task?.resumable && !running && !hasPending && (
              <button type="button" className="ws-btn ws-btn-primary" onClick={() => void handleResume()}>
                <svg className="ws-ico ws-ico-sm" viewBox="0 0 24 24" aria-hidden>
                  <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                繼續執行
              </button>
            )}
            {task && onOpenTrace && (
              <button type="button" className="ws-btn" onClick={() => onOpenTrace(task.task_id)}>
                軌跡
              </button>
            )}
            {live?.taskState && (
              <button type="button" className="ws-btn" onClick={() => onOpenTask(live.id)}>
                任務頁
              </button>
            )}
            {hasPending && (
              <button
                type="button"
                className="ws-btn ws-btn-primary"
                onClick={() => {
                  setDrawerOpen(true);
                  setDrawerTab('thinking');
                }}
              >
                前往裁決
              </button>
            )}
            <button
              type="button"
              className="ws-btn ws-btn-primary"
              onClick={() => {
                setDrawerOpen(true);
                setDrawerTab('chat');
              }}
            >
              對話
            </button>
          </div>
        </nav>

        {llmConfigured === false && (
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#FF9F0A]/20 bg-[#FF9F0A]/8 px-4 py-2">
            <p className="text-[12px] text-[#FF9F0A]">尚未配置 API。請先加入千問／DeepSeek／Kimi／OpenRouter。</p>
            {onOpenSettings && (
              <button type="button" className="ws-btn" onClick={onOpenSettings}>
                加入 API
              </button>
            )}
          </div>
        )}
        {error && (
          <div className="shrink-0 px-4 pt-3">
            <ErrorState
              kind={error.includes('OPC') || error.includes('護欄') ? 'opc_guard' : 'llm'}
              message={error}
              compact
              onRetry={lastQuery ? onRetry : undefined}
              onDismiss={onDismissError}
            />
          </div>
        )}
        {actError && (
          <div className="shrink-0 px-4 pt-3">
            <ErrorState kind="generic" message={actError} compact onDismiss={() => setActError(null)} />
          </div>
        )}

        <div className="ws-scroll">
          <div className="ws-hero">
            <div className="ws-hero-row">
              <h1 className="ws-title">{title}</h1>
              <div
                className={`ws-pill ${pill.cls}`}
                role="button"
                tabIndex={0}
                onClick={() => {
                  setDrawerOpen(true);
                  if (hasPending) setDrawerTab('thinking');
                }}
              >
                <span className="ws-dot" /> {pill.label}
              </div>
              {eta?.remainingSec != null && running && (
                <div className="ws-btn" style={{ fontSize: 11, padding: '2px 8px' }}>
                  預計剩餘 {formatDurationCompact(eta.remainingSec)}
                </div>
              )}
            </div>
            <p className="ws-sub">
              {task ? `Task ID: ${task.task_id}` : `Session: ${sessionId.slice(0, 8)}`}
              {task?.created_at ? ` · 建立於 ${elapsed(task.created_at)}` : ''}
              {` · 階段: ${phaseLabel}`}
              {model ? ` · 模型: ${model}` : ''}
            </p>
            <L0BiasHint snapshot={task?.raho?.l0} compact />

            <div className="ws-metrics">
              <div className="ws-metric">
                <div className="ws-metric-k">總耗時</div>
                <div className="ws-metric-v">{eta ? formatDurationCompact(eta.elapsedSec) : '—'}</div>
                <div className="ws-metric-s">{running ? `本階段 ${phaseLabel}` : pill.label}</div>
              </div>
              <div className="ws-metric">
                <div className="ws-metric-k">Token 消耗</div>
                <div className="ws-metric-v">{tokens.toLocaleString()}</div>
                <div className="ws-metric-s">{task?.resolved_path === 'company' ? '公司協作' : task?.resolved_path === 'opc' ? 'OPC' : '對話'}</div>
              </div>
              <div className="ws-metric">
                <div className="ws-metric-k">節點成功率</div>
                <div className="ws-metric-v">{successPct}%</div>
                <div className="ws-metric-s">
                  {failN} 失敗 / {totalN || 0} 總計
                </div>
              </div>
              <div className="ws-metric">
                <div className="ws-metric-k">預估成本</div>
                <div className="ws-metric-v">${spent.toFixed(3)}</div>
                <div className="ws-metric-s">上限 ${limit.toFixed(2)}</div>
              </div>
            </div>
          </div>

          <div className="ws-kanban">
            {WS_KANBAN_COLUMNS.map((col) => {
              const rows = nodes.filter((n) => n.column === col.key);
              const color =
                col.key === 'executing' ? 'var(--ws-orange)' : col.key === 'review' ? 'var(--ws-purple)' : 'var(--ws-dim)';
              return (
                <div key={col.key} className="ws-col">
                  <div className="ws-col-h">
                    <div className="ws-col-t">
                      <span style={{ color }}>●</span> {col.label}
                    </div>
                    <div className="ws-col-n">{rows.length}</div>
                  </div>
                  <div className="ws-col-b">
                    {rows.length === 0 && <p className="ws-empty">尚無{col.label}節點</p>}
                    {rows.map((row) => {
                      const label = roleLabel(row.item.assignee || 'developer');
                      const meta = ITEM_STATUS_META[row.status];
                      const barCls =
                        col.key === 'executing' ? ' is-run' : col.key === 'review' && row.status !== 'done' ? ' is-rev' : row.status === 'done' ? ' is-ok' : '';
                      const clock = nodeElapsed(
                        row.item.created_at,
                        row.item.updated_at,
                        now,
                        col.key === 'executing' && running,
                      );
                      return (
                        <button
                          key={row.item.id}
                          type="button"
                          className={`ws-node${selectedId === row.item.id ? ' is-on' : ''}`}
                          onClick={() => {
                            setSelectedId(row.item.id);
                            setDrawerOpen(true);
                            setDrawerTab('thinking');
                            const hit = files.find((f) => f.itemId === row.item.id);
                            if (hit) setFileId(hit.id);
                          }}
                        >
                          <div className="ws-node-id">{nodeCode(row.item.id)}</div>
                          <div className="ws-node-t">{row.item.title}</div>
                          {row.action && col.key === 'executing' && <div className="ws-node-act">{row.action}</div>}
                          {row.tags.length > 0 && (
                            <div className="ws-tags">
                              {row.tags.map((tag) => (
                                <span key={tag} className="ws-tag">
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                          <div className={`ws-bar${barCls}`}>
                            <i style={{ width: `${row.progress}%` }} />
                          </div>
                          <div className="ws-node-f">
                            <div className="ws-user">
                              <span className="ws-ava" style={{ background: avatarColor(row.item.assignee || 'a') }}>
                                {avatarInitial(label)}
                              </span>
                              {label}
                            </div>
                            <div
                              className="ws-node-time"
                              style={col.key === 'executing' ? { color: 'var(--ws-orange)' } : undefined}
                            >
                              {clock || meta?.label || row.status}
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <ChatBottomPanel
          collapsed={bottomOff}
          onToggle={() => setBottomOff((v) => !v)}
          tab={bottomTab}
          onTab={(t) => {
            setBottomTab(t);
            setBottomOff(false);
          }}
          files={files}
          fileId={fileId}
          onFile={setFileId}
          terminal={terminal}
          problems={problems}
          onProblem={() => {
            setDrawerOpen(true);
            setDrawerTab('thinking');
          }}
        />
      </div>

      <ChatNodeDrawer
        open={drawerOpen}
        nodeId={selected ? nodeCode(selected.item.id) : task ? `TASK` : 'CHAT'}
        title={selected?.item.title || title}
        tab={drawerTab}
        onTab={setDrawerTab}
        onClose={() => {
          if (hasPending) setDrawerTab('thinking');
          else setDrawerOpen(false);
        }}
        thinking={thinking}
        files={nodeFiles}
        fileId={fileId}
        onFile={setFileId}
        chatCount={messages.length}
        decision={
          task ? (
            <RahoDecisionBar
              pending={pending}
              runId={task.raho?.run_id}
              poll
              variant="chat"
              onPendingChange={onDecisionPending}
              onResolved={onDecisionResolved}
            />
          ) : null
        }
        chat={
          <MessageList
            messages={messages}
            sessionId={sessionId}
            loading={loading}
            onOpenTask={onOpenTask}
            onOpenTrace={onOpenTrace}
            onSuggest={onSuggest}
            sending={sending}
            onGrillAnswer={onGrillAnswer}
            onBattlePick={onBattlePick}
            variant="drawer"
          />
        }
        composer={
          <InputBar disabled={sending || grilling || waitingBattle} onSend={onSend} compact />
        }
        onAccept={() => {
          setToast(`已接受 ${nodeFiles.length || files.length} 個文件的變更`);
          window.setTimeout(() => setToast(null), 3000);
        }}
      />
      <div className={`ws-toast${toast ? ' is-on' : ''}`}>
        <svg className="ws-ico ws-toast-ico" viewBox="0 0 24 24" aria-hidden>
          <path d="M5 13l4 4L19 7" />
        </svg>
        <span>{toast || '操作成功'}</span>
      </div>
    </div>
  );
}
