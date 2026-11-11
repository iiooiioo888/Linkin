/**
 * ChatView 任務確認面板：草案／席位／實體寫入與開工／拒絕。
 */
import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import {
  applySeatOverride,
  commitNarrative,
  decideBudget,
  fetchTask,
  retryFieldWrites,
  updateConfirmationDraft,
} from '../../api/client';
import type { ChatMessage, TaskProgress } from '../../types';

interface ChatConfirmPanelProps {
  messages: ChatMessage[];
  setActError: Dispatch<SetStateAction<string | null>>;
  onTaskStatePatch?: (taskId: string, patch: Partial<TaskProgress> | TaskProgress) => void;
}

export function ChatConfirmPanel({ messages, setActError, onTaskStatePatch }: ChatConfirmPanelProps) {
  const confirmTask = [...messages].reverse().find((m) => m.taskState?.status === 'awaiting_confirmation')?.taskState;
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [draftName, setDraftName] = useState('');
  const [draftPrompt, setDraftPrompt] = useState('');
  const [seatRole, setSeatRole] = useState('manager');
  const [seatPrompt, setSeatPrompt] = useState('');
  const [entityKind, setEntityKind] = useState<'npc' | 'quest' | 'item'>('quest');
  const [entityName, setEntityName] = useState('');

  useEffect(() => {
    const seat = confirmTask?.budget_plan?.new_seats?.[0];
    setDraftName(seat?.name || '');
    setDraftPrompt(seat?.system_prompt || '');
  }, [confirmTask?.task_id]);

  const handleBudget = async (action: 'approve' | 'reject') => {
    if (!confirmTask) return;
    setConfirmBusy(true);
    setActError(null);
    try {
      await decideBudget(confirmTask.task_id, action);
      const next = await fetchTask(confirmTask.task_id);
      onTaskStatePatch?.(confirmTask.task_id, next);
    } catch (err) {
      setActError((err as Error).message);
    } finally {
      setConfirmBusy(false);
    }
  };

  const refreshConfirm = async () => {
    if (!confirmTask) return;
    const next = await fetchTask(confirmTask.task_id);
    onTaskStatePatch?.(confirmTask.task_id, next);
  };

  const saveNewSeatDraft = async () => {
    if (!confirmTask) return;
    setConfirmBusy(true);
    setActError(null);
    try {
      await updateConfirmationDraft(confirmTask.task_id, {
        new_seats: [{ name: draftName, system_prompt: draftPrompt, tools_allowed: confirmTask.budget_plan?.new_seats?.[0]?.tools_allowed || [] }],
      });
      await refreshConfirm();
    } catch (err) {
      setActError((err as Error).message);
    } finally {
      setConfirmBusy(false);
    }
  };

  const saveSeatOverride = async () => {
    if (!confirmTask || !seatRole.trim()) return;
    setConfirmBusy(true);
    setActError(null);
    try {
      await applySeatOverride(confirmTask.task_id, { role_id: seatRole.trim(), system_prompt: seatPrompt });
      await refreshConfirm();
    } catch (err) {
      setActError((err as Error).message);
    } finally {
      setConfirmBusy(false);
    }
  };

  const saveNarrative = async () => {
    if (!confirmTask || !entityName.trim()) return;
    setConfirmBusy(true);
    setActError(null);
    try {
      await commitNarrative(confirmTask.task_id, entityKind, { name: entityName.trim() });
      setEntityName('');
      await refreshConfirm();
    } catch (err) {
      setActError((err as Error).message);
    } finally {
      setConfirmBusy(false);
    }
  };

  return confirmTask ? (
    <div className="shrink-0 border-b border-white/10 px-4 py-3 sm:px-6">
      <p className="text-[13px] font-medium text-[var(--console-ink)]">確認</p>
      <p className="mt-1 text-[12px] text-[var(--console-sub)]">
        {confirmTask.budget_plan?.execution_plan || confirmTask.budget_plan?.note || '任務經理正在整理草案。點頭前不會開工。世界觀這一輪只讀。'}
      </p>
      {!!confirmTask.budget_plan?.lines?.length && (
        <ul className="mt-2 space-y-1 text-[12px] text-[var(--console-sub)]">
          {confirmTask.budget_plan.lines.slice(0, 6).map((line) => (
            <li key={line.line_id || line.title}>
              {line.title || '子項'} · {line.assignee || '未指派'} · {line.assumption || '未登記'}
            </li>
          ))}
        </ul>
      )}
      {!!confirmTask.budget_plan?.seat_overrides?.length && (
        <ul className="mt-2 space-y-1 text-[12px] text-[var(--console-sub)]">
          {confirmTask.budget_plan.seat_overrides.map((row) => (
            <li key={row.role_id}>
              席位 {row.role_id} {row.applied ? '已寫入目錄' : `未寫入：${row.reason || ''}`}
            </li>
          ))}
        </ul>
      )}
      {!!confirmTask.budget_plan?.new_seats?.length && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <input
            value={draftName}
            onChange={(event) => setDraftName(event.target.value)}
            placeholder="新席位名稱"
            className="rounded border border-white/15 bg-transparent px-2 py-1 text-[12px]"
          />
          <input
            value={draftPrompt}
            onChange={(event) => setDraftPrompt(event.target.value)}
            placeholder="新席位提示詞"
            className="min-w-40 flex-1 rounded border border-white/15 bg-transparent px-2 py-1 text-[12px]"
          />
          <button type="button" disabled={confirmBusy} onClick={() => void saveNewSeatDraft()} className="rounded border border-white/15 px-2 py-1 text-[12px]">
            儲存草稿
          </button>
        </div>
      )}
      {!!confirmTask.budget_plan?.field_writes?.length && (
        <ul className="mt-2 space-y-1 text-[12px] text-[var(--console-sub)]">
          {confirmTask.budget_plan.field_writes.map((row) => (
            <li key={row.tag}>現場 {row.tag} = {String(row.value ?? '')}</li>
          ))}
        </ul>
      )}
      {confirmTask.budget_plan?.field_writes_result?.status === 'blocked' && (
        <div className="mt-2 text-[12px] text-[var(--console-amber)]">
          <p>現場寫入未執行，任務維持開工。</p>
          <button
            type="button"
            disabled={confirmBusy}
            onClick={() => {
              setConfirmBusy(true);
              void retryFieldWrites(confirmTask.task_id)
                .then(refreshConfirm)
                .catch((err) => setActError((err as Error).message))
                .finally(() => setConfirmBusy(false));
            }}
            className="mt-1 rounded border border-white/15 px-2 py-1 text-[var(--console-ink)]"
          >
            重新檢查
          </button>
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input value={seatRole} onChange={(event) => setSeatRole(event.target.value)} placeholder="席位 id" className="w-28 rounded border border-white/15 bg-transparent px-2 py-1 text-[12px]" />
        <input value={seatPrompt} onChange={(event) => setSeatPrompt(event.target.value)} placeholder="提示詞，立刻寫入目錄" className="min-w-40 flex-1 rounded border border-white/15 bg-transparent px-2 py-1 text-[12px]" />
        <button type="button" disabled={confirmBusy} onClick={() => void saveSeatOverride()} className="rounded border border-white/15 px-2 py-1 text-[12px]">寫入席位</button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select value={entityKind} onChange={(event) => setEntityKind(event.target.value as 'npc' | 'quest' | 'item')} className="rounded border border-white/15 bg-transparent px-2 py-1 text-[12px]">
          <option value="quest">quest</option>
          <option value="npc">npc</option>
          <option value="item">item</option>
        </select>
        <input value={entityName} onChange={(event) => setEntityName(event.target.value)} placeholder="實體名稱" className="rounded border border-white/15 bg-transparent px-2 py-1 text-[12px]" />
        <button type="button" disabled={confirmBusy} onClick={() => void saveNarrative()} className="rounded border border-white/15 px-2 py-1 text-[12px]">寫入實體</button>
      </div>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={confirmBusy || confirmTask.budget_plan?.status !== 'pending_user'}
          onClick={() => void handleBudget('approve')}
          className="rounded-lg bg-[var(--console-accent)] px-3 py-1 text-[12px] text-white disabled:opacity-40"
        >
          確認並開工
        </button>
        <button
          type="button"
          disabled={confirmBusy}
          onClick={() => void handleBudget('reject')}
          className="rounded-lg border border-white/15 px-3 py-1 text-[12px] text-[var(--console-ink)] disabled:opacity-40"
        >
          拒絕
        </button>
      </div>
    </div>
  ) : null;
}
