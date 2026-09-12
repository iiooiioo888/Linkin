/**
 * NarrativeWorkspacePanel — 敘事草稿工作區：建立、編輯草稿、提交至 Linkin 實體。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchL0Kernel } from '../../api/client';
import {
  beginNarrativeWorkspace,
  commitNarrativeWorkspace,
  confirmNarrativeWorkspace,
  fetchNarrativeWorkspace,
  listNarrativeWorkspaces,
  writeNarrativeDraft,
  type NarrativeWorkspace,
} from '../../api/linkin';

const DRAFT_TEMPLATES: Record<string, string> = {
  quest: JSON.stringify(
    {
      title: '支線：遺失的織夢殘章',
      quest_type: '支线',
      difficulty: '普通',
      region: '织庭都',
      description: '在織庭都尋找被風吹散的織夢殘章。',
      player_id: 'traveler-01',
    },
    null,
    2,
  ),
  npc: JSON.stringify(
    {
      name: '敘事草稿·青禾',
      faction: '织庭盟',
      occupation: '巡禮者',
      personality: '沉靜、記性極佳',
      backstory: '在織庭都記錄旅人口述的片段傳說。',
      location: '织庭都',
      speech_style: '白描敘事',
    },
    null,
    2,
  ),
  lore_note: JSON.stringify(
    { title: '設定筆記', text: '織庭都夜裡會聽見金線共鳴。', tags: ['织庭都', '靈丝'] },
    null,
    2,
  ),
  chapter_beat: JSON.stringify(
    { title: '開場', chapter: '第一章', beat_order: 1, text: '旅人抵達織庭都廣場。' },
    null,
    2,
  ),
};

const KNOWN_KEYS = Object.keys(DRAFT_TEMPLATES);

function defaultTaskId() {
  return `task-${Date.now().toString(36)}`;
}

function snapshotFromL0(generatedAt?: number) {
  if (generatedAt) return `snap-${Math.floor(generatedAt)}`;
  return 'snap-local';
}

export default function NarrativeWorkspacePanel() {
  const [taskId, setTaskId] = useState(defaultTaskId);
  const [snapshotId, setSnapshotId] = useState('snap-local');
  const [workspace, setWorkspace] = useState<NarrativeWorkspace | null>(null);
  const [draftEditors, setDraftEditors] = useState<Record<string, string>>({});
  const [selectedKey, setSelectedKey] = useState('quest');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const awaitingConfirmation = workspace?.state === 'awaiting_confirmation';
  const isTerminal = workspace?.state === 'committed' || workspace?.state === 'discarded';

  const loadSnapshot = useCallback(async () => {
    try {
      const l0 = await fetchL0Kernel();
      setSnapshotId(snapshotFromL0(l0.generated_at));
    } catch {
      setSnapshotId('snap-local');
    }
  }, []);

  const syncEditors = useCallback((ws: NarrativeWorkspace) => {
    const next: Record<string, string> = {};
    for (const key of KNOWN_KEYS) {
      const value = ws.drafts?.[key];
      next[key] = value !== undefined ? JSON.stringify(value, null, 2) : DRAFT_TEMPLATES[key] ?? '{}';
    }
    for (const key of ws.draft_keys ?? []) {
      if (!(key in next) && ws.drafts?.[key] !== undefined) {
        next[key] = JSON.stringify(ws.drafts[key], null, 2);
      }
    }
    setDraftEditors(next);
  }, []);

  const refreshWorkspace = useCallback(async (workspaceId: string) => {
    const data = await fetchNarrativeWorkspace(workspaceId);
    setWorkspace(data.workspace);
    syncEditors(data.workspace);
  }, [syncEditors]);

  const resumeTaskWorkspace = useCallback(async () => {
    const listed = await listNarrativeWorkspaces(taskId);
    if (listed.workspaces.length > 0) {
      await refreshWorkspace(listed.workspaces[0].workspace_id);
    }
  }, [refreshWorkspace, taskId]);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    void resumeTaskWorkspace().catch(() => undefined);
  }, [resumeTaskWorkspace]);

  const stateLabel = useMemo(() => {
    switch (workspace?.state) {
      case 'active':
        return '編輯中';
      case 'awaiting_confirmation':
        return '快照衝突 · 待確認';
      case 'committed':
        return '已提交';
      case 'discarded':
        return '已丟棄';
      default:
        return '尚未建立';
    }
  }, [workspace?.state]);

  const onBegin = async () => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await beginNarrativeWorkspace({ task_id: taskId, snapshot_id: snapshotId });
      setWorkspace(data.workspace);
      syncEditors(data.workspace);
      setSuccess('工作區已建立，可開始編輯草稿。');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onSaveDraft = async () => {
    if (!workspace) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const raw = draftEditors[selectedKey] ?? '{}';
      const parsed = JSON.parse(raw) as unknown;
      const data = await writeNarrativeDraft(workspace.workspace_id, selectedKey, parsed);
      setWorkspace(data.workspace);
      syncEditors(data.workspace);
      setSuccess(`草稿「${selectedKey}」已儲存至工作區。`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onCommit = async () => {
    if (!workspace) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await commitNarrativeWorkspace(workspace.workspace_id);
      setWorkspace(data.workspace);
      const ids = Object.entries(data.committed ?? {})
        .map(([key, val]) => `${key}:${(val as { id?: string }).id ?? 'ok'}`)
        .join(' · ');
      setSuccess(ids ? `提交成功：${ids}` : '提交成功');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onConfirm = async (choice: 'rebind' | 'discard') => {
    if (!workspace) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await confirmNarrativeWorkspace(workspace.workspace_id, {
        choice,
        new_snapshot_id: choice === 'rebind' ? snapshotId : undefined,
      });
      setWorkspace(data.workspace);
      syncEditors(data.workspace);
      setSuccess(choice === 'rebind' ? '已重綁新快照，可繼續編輯或提交。' : '草稿已丟棄。');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-[#c9a961]">敘事工作區</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            草稿僅存於記憶體；提交後寫入 Linkin 任務／NPC／設定，不維護第二套世界觀圖譜。
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadSnapshot()}
          className="rounded-xl border border-[#c9a961]/30 px-2 py-1 text-[11px] text-[#c9a961]"
        >
          重新讀取 L0 快照
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      )}
      {success && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {success}
        </div>
      )}

      <div className="mb-4 grid gap-2 rounded-xl border border-[#c9a961]/20 bg-[#1C1C1E] p-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-[10px] text-[#8a8f98]">
          任務 ID
          <input
            value={taskId}
            onChange={(e) => setTaskId(e.target.value)}
            disabled={Boolean(workspace) && !isTerminal}
            className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
          />
        </label>
        <label className="text-[10px] text-[#8a8f98]">
          L0 快照 ID
          <input
            value={snapshotId}
            onChange={(e) => setSnapshotId(e.target.value)}
            disabled={Boolean(workspace) && !isTerminal}
            className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
          />
        </label>
        <div className="flex flex-col justify-end text-[11px] text-[#8a8f98]">
          <span>
            狀態：<span className="text-[#c9a961]">{stateLabel}</span>
          </span>
          {workspace && (
            <span className="truncate text-[10px] text-[#636366]">工作區 {workspace.workspace_id}</span>
          )}
        </div>
        <div className="flex items-end">
          <button
            type="button"
            disabled={busy || (Boolean(workspace) && !isTerminal)}
            onClick={() => void onBegin()}
            className="w-full rounded-lg border border-[#c9a961]/40 bg-[#c9a961]/10 px-3 py-1.5 text-[12px] text-[#c9a961] disabled:opacity-40"
          >
            {busy ? '處理中…' : workspace && !isTerminal ? '工作區進行中' : '建立工作區'}
          </button>
        </div>
      </div>

      {awaitingConfirmation && workspace && (
        <div className="mb-4 rounded-xl border border-[#FF9F0A]/40 bg-[#FF9F0A]/10 p-3">
          <p className="text-[12px] text-[#FF9F0A]">L0 快照已更新，請選擇保留草稿並重綁，或丟棄草稿。</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void onConfirm('rebind')}
              className="rounded-lg border border-[#c9a961]/40 bg-[#c9a961]/10 px-3 py-1.5 text-[12px] text-[#c9a961]"
            >
              重綁新快照
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => void onConfirm('discard')}
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-[12px] text-red-300"
            >
              丟棄草稿
            </button>
          </div>
        </div>
      )}

      {workspace && !isTerminal && (
        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-2">
            <p className="mb-2 px-1 text-[10px] text-[#8a8f98]">草稿鍵</p>
            <div className="space-y-1">
              {KNOWN_KEYS.map((key) => {
                const saved = workspace.draft_keys?.includes(key);
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setSelectedKey(key)}
                    className={`flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[12px] ${
                      selectedKey === key
                        ? 'border border-[#c9a961]/40 bg-[#c9a961]/10 text-[#c9a961]'
                        : 'border border-transparent text-[#AEAEB2] hover:bg-white/[0.04]'
                    }`}
                  >
                    <span>{key}</span>
                    {saved && <span className="text-[10px] text-emerald-400">已存</span>}
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="flex min-h-[280px] flex-col rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[13px] font-medium">編輯草稿 · {selectedKey}</h3>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={busy || awaitingConfirmation}
                  onClick={() => void onSaveDraft()}
                  className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[#AEAEB2] disabled:opacity-40"
                >
                  儲存草稿
                </button>
                <button
                  type="button"
                  disabled={busy || awaitingConfirmation}
                  onClick={() => void onCommit()}
                  className="rounded-lg border border-[#c9a961]/40 bg-[#c9a961]/10 px-3 py-1.5 text-[12px] text-[#c9a961] disabled:opacity-40"
                >
                  提交至 Linkin
                </button>
              </div>
            </div>
            <textarea
              value={draftEditors[selectedKey] ?? '{}'}
              onChange={(e) => setDraftEditors((prev) => ({ ...prev, [selectedKey]: e.target.value }))}
              spellCheck={false}
              className="min-h-[220px] flex-1 resize-y rounded-lg border border-white/[0.08] bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-[#f7f8f8]"
            />
            <p className="mt-2 text-[10px] text-[#636366]">
              支援 quest、npc、lore_note、chapter_beat；提交時寫入既有 Linkin store。
            </p>
          </section>
        </div>
      )}

      {workspace?.state === 'committed' && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-[12px] text-emerald-200">
          此工作區已提交。可變更任務 ID 後建立新的工作區繼續編輯。
        </div>
      )}
    </div>
  );
}
