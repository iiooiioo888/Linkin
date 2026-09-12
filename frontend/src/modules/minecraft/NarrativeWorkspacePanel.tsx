/**
 * NarrativeWorkspacePanel — Phase 0 故事草稿工作區（完整 RPG 管線的起點）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchL0Kernel } from '../../api/client';
import {
  beginNarrativeWorkspace,
  commitNarrativeWorkspace,
  confirmNarrativeWorkspace,
  fetchNarrativeWorkspace,
  listNarrativeWorkspaces,
  generateNarrativeDrafts,
  seedNarrativeStarterPack,
  writeNarrativeDraft,
  type NarrativeWorkspace,
} from '../../api/linkin';

const DRAFT_LABELS: Record<string, string> = {
  story_arc: '故事主線',
  quest: '任務',
  npc: 'NPC',
  item: '道具',
  build_brief: '建築／地圖意圖',
};

const DRAFT_TEMPLATES: Record<string, string> = {
  story_arc: JSON.stringify(
    {
      title: '靈丝残章',
      summary: '旅人在織庭都追尋失落的織夢記憶，串連 NPC、任務與建築意圖。',
      region: '织庭都',
      chapters: ['序章：抵達織庭都', '第一章：追尋殘章'],
      tags: ['主線', '织庭都'],
    },
    null,
    2,
  ),
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
  item: JSON.stringify(
    {
      name: '靈丝殘章',
      type: '消耗品',
      rarity: 'common',
      attributes: { power: 12 },
      description: '與主線共鳴的碎片，可觸發後續任務。',
    },
    null,
    2,
  ),
  build_brief: JSON.stringify(
    {
      title: '織庭都序章廣場',
      region: '织庭都',
      location: '0,64,0',
      style: '织庭盟',
      prompt: '帶金線紋樣的開場廣場，中央有契約碑。',
      block_count: 800,
      notes: 'Phase 0 僅落庫意圖；提交後由 Builder／MineMCP 管線消費（Phase 2）。',
    },
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
  const [theme, setTheme] = useState('靈丝残章');
  const [region, setRegion] = useState('织庭都');
  const [brief, setBrief] = useState('');
  const [workspace, setWorkspace] = useState<NarrativeWorkspace | null>(null);
  const [draftEditors, setDraftEditors] = useState<Record<string, string>>({});
  const [selectedKey, setSelectedKey] = useState('story_arc');
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
        return '已提交至實體庫';
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
      setSuccess('Phase 0 工作區已建立。可手動編輯或使用「一鍵草案」。');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onGenerate = async () => {
    if (!workspace) return;
    const trimmed = brief.trim();
    if (!trimmed) {
      setError('請先輸入 brief（故事種子／主題描述）。');
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await generateNarrativeDrafts(workspace.workspace_id, {
        brief: trimmed,
        locale: 'zh-Hant',
        region,
        theme,
      });
      setWorkspace(data.workspace);
      syncEditors(data.workspace);
      const labels = data.replaced_keys.map((k) => DRAFT_LABELS[k] ?? k).join('、');
      setSuccess(
        `AI 已覆寫 ${labels || '草案'}。請審閱各鍵內容後再按「提交至 Linkin」。`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onStarterPack = async () => {
    if (!workspace) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await seedNarrativeStarterPack(workspace.workspace_id, { region, theme });
      setWorkspace(data.workspace);
      syncEditors(data.workspace);
      setSuccess(
        data.source === 'llm'
          ? 'AI 已填入一組 RPG 草案（故事／任務／NPC／道具／建築意圖）。請審閱後按「提交」。'
          : '已填入本地模板草案。請審閱後按「提交至 Linkin」。',
      );
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
      setSuccess(`草稿「${DRAFT_LABELS[selectedKey] ?? selectedKey}」已儲存。`);
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
        .map(([key, val]) => `${DRAFT_LABELS[key] ?? key}:${(val as { id?: string }).id ?? 'ok'}`)
        .join(' · ');
      setSuccess(
        ids
          ? `已寫入 Linkin 實體庫：${ids}。後續可驅動地圖配置與 MineMCP 建造（Phase 2+）。`
          : '提交成功',
      );
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
      <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
        <div className="max-w-2xl">
          <p className="text-[10px] uppercase tracking-wide text-[#c9a961]/80">Phase 1 · 故事草稿工作區</p>
          <h2 className="text-sm font-semibold text-[#c9a961]">RPG 草案桌</h2>
          <p className="mt-1 text-[11px] leading-relaxed text-[#8a8f98]">
            北極星：AI 生成完整 Minecraft RPG（故事、NPC、地圖、建築、道具）。
            輸入 brief 後按「AI 生成」可一次填入五個草案鍵（覆寫該鍵既有內容）；審閱後再提交至 Linkin 實體庫。
            不會自動寫入世界觀或觸發 MineMCP 建造。
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

      <div className="mb-4 grid gap-2 rounded-xl border border-[#c9a961]/20 bg-[#1C1C1E] p-3 sm:grid-cols-2 lg:grid-cols-6">
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
        <label className="text-[10px] text-[#8a8f98]">
          區域
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
          >
            <option value="织庭都">織庭都</option>
            <option value="精灵森林">精靈森林</option>
            <option value="裂隙港">裂隙港</option>
            <option value="宁渊谷">寧淵谷</option>
          </select>
        </label>
        <label className="text-[10px] text-[#8a8f98]">
          主題
          <input
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
          />
        </label>
        <div className="flex flex-col justify-end text-[11px] text-[#8a8f98]">
          <span>
            狀態：<span className="text-[#c9a961]">{stateLabel}</span>
          </span>
          {workspace && (
            <span className="truncate text-[10px] text-[#636366]">{workspace.workspace_id}</span>
          )}
        </div>
        <div className="flex flex-col justify-end gap-1">
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
        <>
          <div className="mb-4 rounded-xl border border-[#c9a961]/20 bg-[#121216] p-3">
            <label className="block text-[10px] text-[#8a8f98]">
              Brief（故事種子／主題描述）
              <textarea
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
                disabled={busy || awaitingConfirmation}
                placeholder="例：旅人在織庭都發現失落的靈丝契約，需與典章抄錄者合作揭開三大陣營的秘密…"
                rows={3}
                className="mt-1 w-full resize-y rounded-lg border border-white/[0.08] bg-[#08080a] px-3 py-2 text-[12px] leading-relaxed text-[#f7f8f8] placeholder:text-[#636366] disabled:opacity-50"
              />
            </label>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                disabled={busy || awaitingConfirmation || !brief.trim()}
                onClick={() => void onGenerate()}
                className="rounded-lg border border-[#c9a961]/50 bg-[#c9a961]/15 px-4 py-1.5 text-[12px] font-medium text-[#c9a961] disabled:opacity-40"
              >
                {busy ? '生成中…' : 'AI 生成'}
              </button>
              <span className="text-[10px] text-[#636366]">
                覆寫五個草案鍵；不會自動提交。區域／主題欄位會作為生成上下文。
              </span>
            </div>
          </div>

          <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="rounded-xl border border-white/[0.08] bg-[#121216] p-2">
            <p className="mb-2 px-1 text-[10px] text-[#8a8f98]">RPG 草案鍵</p>
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
                    <span>{DRAFT_LABELS[key] ?? key}</span>
                    {saved && <span className="text-[10px] text-emerald-400">已存</span>}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              disabled={busy || awaitingConfirmation}
              onClick={() => void onStarterPack()}
              className="mt-3 w-full rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-2 py-1.5 text-[11px] text-[#64D2FF] disabled:opacity-40"
            >
              一鍵草案（AI／模板）
            </button>
          </aside>

          <section className="flex min-h-[280px] flex-col rounded-xl border border-white/[0.08] bg-[#121216] p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[13px] font-medium">
                編輯 · {DRAFT_LABELS[selectedKey] ?? selectedKey}
                <span className="ml-2 text-[10px] font-normal text-[#636366]">{selectedKey}</span>
              </h3>
              <div className="flex flex-wrap gap-2">
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
            <p className="mt-2 text-[10px] leading-relaxed text-[#636366]">
              提交後：story_arc → 主線實體；quest／npc／item → 既有 store；build_brief → 建築意圖實體（Phase 2 Builder／MineMCP 消費）。
            </p>
          </section>
        </div>
        </>
      )}

      {workspace?.state === 'committed' && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-[12px] leading-relaxed text-emerald-200">
          草案已寫入 Linkin 實體庫。下一步：在任務／NPC／道具／建築面板檢視成果；地圖生成與 MineMCP 即時建造將在後續 Phase 接入。
        </div>
      )}
    </div>
  );
}
