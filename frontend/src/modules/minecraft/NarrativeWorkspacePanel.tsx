/**
 * NarrativeWorkspacePanel — Phase 0 故事草稿工作區（完整 RPG 管線的起點）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchL0Kernel } from '../../api/client';
import {
  applyBuildBrief,
  applyMapPlan,
  applyWorldIntents,
  beginNarrativeWorkspace,
  commitNarrativeWorkspace,
  confirmNarrativeWorkspace,
  fetchBuildBrief,
  fetchBuildBriefs,
  fetchMinecraftStatus,
  fetchNarrativeWorkspace,
  fetchPendingWorldIntents,
  generateMapPlan,
  generateNarrativeDrafts,
  listNarrativeWorkspaces,
  previewBuildBrief,
  previewMapPlan,
  previewWorldIntents,
  runNarrativePipeline,
  seedNarrativeStarterPack,
  writeNarrativeDraft,
  type BuildBrief,
  type BuildBriefApplyResult,
  type BuildBriefPreview,
  type MapPlan,
  type MapPlanPreview,
  type MinecraftStatus,
  type NarrativePipelineResult,
  type NarrativeWorkspace,
  type PendingWorldIntents,
  type PipelineStep,
  type PipelineStepStatus,
  type WorldIntentApplyResult,
  type WorldIntentPreview,
} from '../../api/linkin';
import { consoleLayout } from '../../lib/consoleLayout';
import { NARRATIVE_REGION_OPTIONS } from './localeRegions';
import { McHeader, McPage } from './McChrome';

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
      notes: '先記入草稿。提交後不會自動放進遊戲，需再手動落地。',
    },
    null,
    2,
  ),
};

const KNOWN_KEYS = Object.keys(DRAFT_TEMPLATES);

const PHASE4_STEPS = ['brief', 'generate', 'preview', 'apply'] as const;
type Phase4Step = (typeof PHASE4_STEPS)[number];

const PHASE4_LABELS: Record<Phase4Step, string> = {
  brief: '草稿',
  generate: '生成',
  preview: '預覽',
  apply: '落地',
};

const PIPELINE_STEP_LABELS: Record<string, string> = {
  begin_workspace: '建立工作區',
  generate: 'AI 生成草案',
  commit: '提交至 Linkin',
  map_generate: '生成區域地圖',
  build_preview: '建築預覽',
  world_preview: '世界意圖預覽',
  map_preview: '地圖預覽',
  build_apply: '落地建築',
  world_apply: '落地 NPC／任務／道具',
  map_apply: '落地地圖',
};

const PIPELINE_STATUS_STYLES: Record<PipelineStepStatus, string> = {
  pending: 'text-[var(--console-sub)]',
  running: 'text-[var(--console-accent)]',
  ok: 'text-emerald-400',
  error: 'text-red-400',
  partial: 'text-[var(--console-amber)]',
  skipped: 'text-[var(--console-sub)]',
};

const PIPELINE_STATUS_LABEL: Record<PipelineStepStatus, string> = {
  pending: '等待',
  running: '進行中',
  ok: '完成',
  error: '失敗',
  partial: '部分完成',
  skipped: '略過',
};

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
  const [mapSeed, setMapSeed] = useState('');
  const [mapPlan, setMapPlan] = useState<MapPlan | null>(null);
  const [mapPreview, setMapPreview] = useState<MapPlanPreview | null>(null);
  const [mapStep, setMapStep] = useState<Phase4Step>('brief');
  const [mapNote, setMapNote] = useState<string | null>(null);
  const [committedBriefId, setCommittedBriefId] = useState<string | null>(null);
  const [buildBrief, setBuildBrief] = useState<BuildBrief | null>(null);
  const [briefPreview, setBriefPreview] = useState<BuildBriefPreview | null>(null);
  const [applyResult, setApplyResult] = useState<BuildBriefApplyResult | null>(null);
  const [bridgeStatus, setBridgeStatus] = useState<MinecraftStatus | null>(null);
  const [buildBusy, setBuildBusy] = useState<'idle' | 'preview' | 'apply'>('idle');
  const [pendingWorld, setPendingWorld] = useState<PendingWorldIntents | null>(null);
  const [worldPreview, setWorldPreview] = useState<WorldIntentPreview[] | null>(null);
  const [worldApplyResult, setWorldApplyResult] = useState<WorldIntentApplyResult | null>(null);
  const [worldBusy, setWorldBusy] = useState<'idle' | 'preview' | 'apply'>('idle');
  const [pipelineBusy, setPipelineBusy] = useState(false);
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStep[]>([]);
  const [pipelineResult, setPipelineResult] = useState<NarrativePipelineResult | null>(null);
  const [pipelineConfirmWorld, setPipelineConfirmWorld] = useState(false);

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

  const refreshBridgeStatus = useCallback(async () => {
    try {
      const status = await fetchMinecraftStatus();
      setBridgeStatus(status);
    } catch {
      setBridgeStatus(null);
    }
  }, []);

  const loadCommittedBrief = useCallback(async (briefId: string) => {
    try {
      const data = await fetchBuildBrief(briefId);
      setBuildBrief(data.build_brief);
      setCommittedBriefId(briefId);
    } catch {
      setBuildBrief(null);
    }
  }, []);

  const refreshPendingWorld = useCallback(async () => {
    try {
      const data = await fetchPendingWorldIntents();
      setPendingWorld(data.pending);
    } catch {
      setPendingWorld(null);
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    void resumeTaskWorkspace().catch(() => undefined);
  }, [resumeTaskWorkspace]);

  useEffect(() => {
    if (workspace?.state === 'committed') {
      void refreshPendingWorld();
    }
  }, [workspace?.state, refreshPendingWorld]);

  useEffect(() => {
    if (workspace?.state !== 'committed' || committedBriefId) return;
    void (async () => {
      try {
        const listed = await fetchBuildBriefs();
        const draft = workspace.drafts?.build_brief as { title?: string } | undefined;
        const candidates = listed.build_briefs.filter(
          (b) => b.source === 'narrative_workspace' || b.status === 'pending_builder' || b.status === 'built',
        );
        const match =
          (draft?.title ? candidates.find((b) => b.title === draft.title) : undefined) ??
          candidates[candidates.length - 1];
        if (match) {
          setCommittedBriefId(match.id);
          setBuildBrief(match);
          await refreshBridgeStatus();
        }
      } catch {
        /* ignore */
      }
    })();
  }, [workspace, committedBriefId, refreshBridgeStatus]);

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
      setSuccess('工作區已建立。可以手動編輯，或直接產生草案。');
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
      const schools = [...new Set((data.agents ?? []).map((agent) => agent.school))].join('、');
      setSuccess(
        schools
          ? `應用席（${schools}）已覆寫 ${labels || '草案'}。請審閱各鍵內容後再按「提交至 Linkin」。`
          : `AI 已覆寫 ${labels || '草案'}。請審閱各鍵內容後再按「提交至 Linkin」。`,
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
      const schools = [...new Set((data.agents ?? []).map((agent) => agent.school))].join('、');
      setSuccess(
        data.source === 'llm'
          ? `應用席${schools ? `（${schools}）` : ''}已填入一組 RPG 草案（故事／任務／NPC／道具／建築意圖）。請審閱後按「提交」。`
          : '已填入本地模板草案（風格與屬性已對齊區域憲法）。請審閱後按「提交至 Linkin」。',
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
    setBriefPreview(null);
    setApplyResult(null);
    setWorldPreview(null);
    setWorldApplyResult(null);
    try {
      const data = await commitNarrativeWorkspace(workspace.workspace_id);
      setWorkspace(data.workspace);
      const brief = data.committed?.build_brief as { id?: string } | undefined;
      if (brief?.id) {
        setCommittedBriefId(brief.id);
        await loadCommittedBrief(brief.id);
        await refreshBridgeStatus();
      }
      await refreshPendingWorld();
      const ids = Object.entries(data.committed ?? {})
        .map(([key, val]) => `${DRAFT_LABELS[key] ?? key}:${(val as { id?: string }).id ?? 'ok'}`)
        .join(' · ');
      setSuccess(
        ids
          ? `已記入：${ids}。建築、NPC、任務與道具還要手動落地，這次提交不會寫進遊戲。`
          : '提交成功',
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onPreviewBuild = async () => {
    if (!committedBriefId) return;
    setBuildBusy('preview');
    setError(null);
    try {
      const data = await previewBuildBrief(committedBriefId);
      setBriefPreview(data);
      await refreshBridgeStatus();
      setSuccess(
        `預覽：約 ${data.bounds.solid_count} 方塊，錨點 (${data.bounds.anchor?.x ?? '?'}, ${data.bounds.anchor?.y ?? '?'}, ${data.bounds.anchor?.z ?? '?'})`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBuildBusy('idle');
    }
  };

  const onPreviewWorld = async () => {
    if (!pendingWorld?.count) return;
    setWorldBusy('preview');
    setError(null);
    try {
      const data = await previewWorldIntents({ apply_all: true });
      setWorldPreview(data.intents);
      await refreshBridgeStatus();
      setSuccess(`預覽 ${data.count} 筆世界意圖（NPC／任務／道具）。`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWorldBusy('idle');
    }
  };

  const onApplyWorld = async () => {
    if (!pendingWorld?.count) return;
    setWorldBusy('apply');
    setError(null);
    setWorldApplyResult(null);
    try {
      const data = await applyWorldIntents({ apply_all: true });
      setWorldApplyResult(data);
      await refreshPendingWorld();
      const { summary } = data;
      setSuccess(
        `世界落地：${summary.overall_status} · 已套用 ${summary.applied} · 部分 ${summary.partial} · 略過 ${summary.skipped}`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWorldBusy('idle');
    }
  };

  const onApplyBuild = async () => {
    if (!committedBriefId) return;
    setBuildBusy('apply');
    setError(null);
    setApplyResult(null);
    try {
      const data = await applyBuildBrief(committedBriefId);
      setApplyResult(data);
      setBuildBrief(data.brief);
      const placement = data.placement;
      const dryNote = placement.dry_run ? '（MineMCP 乾跑／未連線）' : '';
      setSuccess(
        placement.ok
          ? `落地完成：${placement.blocks_placed}/${placement.blocks_total} 方塊${dryNote}`
          : `落地未完成：${placement.blocks_placed}/${placement.blocks_total} 方塊，失敗 ${placement.blocks_failed}`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBuildBusy('idle');
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

  const phase4Index = PHASE4_STEPS.indexOf(mapStep);

  const onGenerateMap = async () => {
    setBusy(true);
    setError(null);
    setSuccess(null);
    setMapNote(null);
    try {
      const data = await generateMapPlan({
        workspace_id: workspace?.workspace_id,
        region,
        seed: mapSeed || theme || region,
      });
      setMapPlan(data.plan);
      setMapPreview(data.preview);
      setMapStep('preview');
      setSuccess(
        data.source === 'llm'
          ? `AI 已生成區域地圖計畫（${data.preview.plot_count} plots）。`
          : `已生成確定性區域佈局（${data.preview.plot_count} plots）。`,
      );
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onRefreshMapPreview = async () => {
    if (!mapPlan) return;
    setBusy(true);
    setError(null);
    try {
      const data = await previewMapPlan({ plan: mapPlan });
      setMapPreview(data.preview);
      setMapStep('preview');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const syncPipelineSideEffects = useCallback(
    async (data: NarrativePipelineResult) => {
      if (data.workspace) {
        setWorkspace(data.workspace);
        syncEditors(data.workspace);
      } else if (data.workspace_id) {
        await refreshWorkspace(data.workspace_id);
      }
      if (data.build_brief_id) {
        setCommittedBriefId(data.build_brief_id);
        await loadCommittedBrief(data.build_brief_id);
      }
      if (data.map_plan) {
        setMapPlan(data.map_plan);
        setMapStep('preview');
      }
      if (data.map_preview) {
        setMapPreview(data.map_preview);
      }
      await refreshBridgeStatus();
      if (data.workspace?.state === 'committed' || data.committed) {
        await refreshPendingWorld();
      }
    },
    [loadCommittedBrief, refreshBridgeStatus, refreshPendingWorld, refreshWorkspace, syncEditors],
  );

  const onRunPipeline = async (confirmWorld = false) => {
    const trimmed = brief.trim();
    if (!workspace && !trimmed && !confirmWorld) {
      setError('請先輸入 brief，或建立工作區後再執行一鍵完整圈。');
      return;
    }
    if (confirmWorld) {
      const proceed = window.confirm(
        '即將寫入 Minecraft 世界（建築／NPC／任務／道具／地圖）。橋接未連線時將以 dry-run 模擬。確定繼續？',
      );
      if (!proceed) return;
    }
    setPipelineBusy(true);
    setError(null);
    setSuccess(null);
    setPipelineSteps([]);
    setPipelineResult(null);
    try {
      const data = await runNarrativePipeline({
        brief: trimmed || undefined,
        workspace_id: workspace?.workspace_id,
        task_id: taskId,
        snapshot_id: snapshotId,
        region,
        theme,
        seed: mapSeed || theme || region,
        confirm_world: confirmWorld,
        regenerate: confirmWorld ? false : Boolean(trimmed),
      });
      setPipelineResult(data);
      setPipelineSteps(data.steps ?? []);
      setPipelineConfirmWorld(false);
      await syncPipelineSideEffects(data);
      const failed = data.steps?.filter((s) => s.status === 'error').length ?? 0;
      const partial = data.steps?.filter((s) => s.status === 'partial').length ?? 0;
      if (data.needs_confirm) {
        setSuccess(
          data.plan?.message ??
            `預覽完成（${data.elapsed_ms ?? 0}ms）。勾選「確認寫入世界」後再按一次以落地。`,
        );
      } else if (failed > 0) {
        setError(`管線完成但有 ${failed} 步失敗；請查看步驟時間軸。`);
      } else if (partial > 0 || data.bridge?.dry_run) {
        setSuccess(
          `一鍵完整圈完成（${data.status}，${data.elapsed_ms ?? 0}ms）。部分步驟為 dry-run／partial。`,
        );
      } else {
        setSuccess(`一鍵完整圈完成（${data.status}，${data.elapsed_ms ?? 0}ms）。`);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPipelineBusy(false);
    }
  };

  const onApplyMap = async () => {
    if (!mapPlan) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    setMapNote(null);
    try {
      const data = await applyMapPlan({ plan: mapPlan, confirm: true });
      setMapPlan(data.plan);
      const note = data.minecraft.dry_run
        ? '橋接未連線：dry-run 模擬落地（未寫入世界）。'
        : `已落地 ${data.minecraft.blocks_placed ?? 0} 方塊（status=${data.status}）。`;
      setMapNote(note);
      setMapStep('apply');
      setSuccess(note);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <McPage>
      <McHeader
        title="敘事工作區"
        lead="從故事草稿走到 NPC、地圖、建築與道具。一鍵完整圈會先生成並預覽，確認後才寫進世界。下方仍可逐步操作。"
        aside={
          <>
            <button type="button" onClick={() => void loadSnapshot()} className="mc-btn">重新讀取態勢</button>
            <button type="button" onClick={() => void refreshBridgeStatus()} className="mc-btn">刷新橋接</button>
          </>
        }
      />
      <div className="mc-workspace">

      <section className="mb-4 rounded-xl border border-[#c9a961]/40 bg-[var(--console-card)] p-4">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-[#c9a961]/80">一鍵完整圈</p>
            <p className="mt-1 text-[11px] text-[#8a8f98]">
              第一次：生成草案、提交、地圖與預覽。第二次（或勾選確認）：落地建築／世界／地圖。
            </p>
          </div>
          <div className="text-[10px] text-[#8a8f98]">
            MineMCP：
            <span className="text-[#c9a961]">
              {bridgeStatus?.enabled
                ? bridgeStatus.connected
                  ? '已連線'
                  : '未連線'
                : '未啟用（乾跑）'}
            </span>
          </div>
        </div>

        {bridgeStatus && (!bridgeStatus.enabled || !bridgeStatus.connected) && (
          <div className="mb-3 rounded-md border border-[color-mix(in_srgb,var(--console-amber)_30%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_10%,transparent)] px-3 py-2 text-[11px] text-[var(--console-amber)]">
            橋接關閉或未連線：管線仍會完成 Linkin 寫入與 dry-run 預覽；世界落地標記為 partial／乾跑。
          </div>
        )}

        <div className="mb-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={pipelineBusy || awaitingConfirmation}
            onClick={() => void onRunPipeline(pipelineConfirmWorld)}
            className="rounded-lg border border-[#c9a961]/50 bg-[#c9a961]/20 px-4 py-2 text-[13px] font-medium text-[#c9a961] disabled:opacity-40"
          >
            {pipelineBusy ? '管線執行中…' : pipelineConfirmWorld ? '一鍵完整圈（確認寫入世界）' : '一鍵完整圈'}
          </button>
          <label className="flex items-center gap-2 text-[11px] text-[var(--console-sub)]">
            <input
              type="checkbox"
              checked={pipelineConfirmWorld}
              onChange={(e) => setPipelineConfirmWorld(e.target.checked)}
              disabled={pipelineBusy}
              className="rounded border-white/20"
            />
            確認寫入世界
          </label>
          {pipelineResult?.needs_confirm && !pipelineConfirmWorld && (
            <span className="text-[10px] text-emerald-400">預覽已完成，可勾選確認後再執行</span>
          )}
        </div>

        {pipelineSteps.length > 0 && (
          <ul className="space-y-1.5 rounded-lg border border-white/[0.06] bg-black/20 p-3">
            {pipelineSteps.map((step) => (
              <li key={step.id} className="flex flex-wrap items-baseline gap-2 text-[11px]">
                <span className={`font-medium ${PIPELINE_STATUS_STYLES[step.status]}`}>
                  {PIPELINE_STATUS_LABEL[step.status]}
                </span>
                <span className="text-[var(--console-ink)]">{step.label ?? PIPELINE_STEP_LABELS[step.id] ?? step.id}</span>
                {step.message && <span className="text-[var(--console-sub)]">— {step.message}</span>}
              </li>
            ))}
          </ul>
        )}

        {pipelineResult && (
          <p className="mt-2 text-[10px] text-[var(--console-sub)]">
            管線{PIPELINE_STATUS_LABEL[pipelineResult.status]}
            {pipelineResult.elapsed_ms ? ` · ${Math.round(pipelineResult.elapsed_ms / 1000)} 秒` : ''}
            {pipelineResult.build_brief_id ? ' · 已產生建築草稿' : ''}
            {pipelineResult.map_plan?.id ? ' · 已產生區域地圖' : ''}
          </p>
        )}
      </section>

      {error && (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      )}
      {success && (
        <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          {success}
        </div>
      )}

      <div className="mb-4 grid gap-2 rounded-xl border border-[#c9a961]/20 bg-[var(--console-card)] p-3 sm:grid-cols-2 lg:grid-cols-6">
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
            {NARRATIVE_REGION_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
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
            <span className="truncate text-[10px] text-[var(--console-sub)]">{workspace.workspace_id}</span>
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
        <div className="mb-4 rounded-xl border border-[color-mix(in_srgb,var(--console-amber)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-amber)_10%,transparent)] p-3">
          <p className="text-[12px] text-[var(--console-amber)]">L0 快照已更新，請選擇保留草稿並重綁，或丟棄草稿。</p>
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
                className="mt-1 w-full resize-y rounded-lg border border-white/[0.08] bg-[#08080a] px-3 py-2 text-[12px] leading-relaxed text-[var(--console-ink)] placeholder:text-[var(--console-sub)] disabled:opacity-50"
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
              <span className="text-[10px] text-[var(--console-sub)]">
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
                        : 'border border-transparent text-[var(--console-sub)] hover:bg-white/[0.04]'
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
              className="mt-3 w-full rounded-lg border border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-2 py-1.5 text-[11px] text-[var(--console-accent)] disabled:opacity-40"
            >
              一鍵草案（AI／模板）
            </button>
          </aside>

          <section className="flex min-h-[280px] flex-col rounded-xl border border-white/[0.08] bg-[#121216] p-3">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[13px] font-medium">
                編輯 · {DRAFT_LABELS[selectedKey] ?? selectedKey}
                <span className="ml-2 text-[10px] font-normal text-[var(--console-sub)]">{selectedKey}</span>
              </h3>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy || awaitingConfirmation}
                  onClick={() => void onSaveDraft()}
                  className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[var(--console-sub)] disabled:opacity-40"
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
              className="min-h-[220px] flex-1 resize-y rounded-lg border border-white/[0.08] bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-[var(--console-ink)]"
            />
            <p className="mt-2 text-[10px] leading-relaxed text-[var(--console-sub)]">
              提交後會記入故事、任務、NPC、道具與建築草稿。遊戲裡還看不到，需再手動落地。
            </p>
          </section>
        </div>
        </>
      )}

      {workspace?.state === 'committed' && (
        <div className="space-y-3">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 text-[12px] leading-relaxed text-emerald-200">
            草案已記入。NPC、任務與道具還在等待落地；建築要另外放下；區域地圖可在下方生成。這次提交不會自動寫進遊戲。
          </div>

          {pendingWorld && pendingWorld.count > 0 && (
            <section className={`${consoleLayout.card} border-[var(--console-accent)]/30 p-4`}>
              <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="mc-kicker">落地 NPC、任務與道具</p>
                  <h3 className={consoleLayout.title}>
                    {pendingWorld.count} 筆待落地意圖
                  </h3>
                  <p className={consoleLayout.subtitle}>
                    NPC {pendingWorld.npcs.length} · 任務 {pendingWorld.quests.length} · 道具 {pendingWorld.items.length}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void refreshBridgeStatus()}
                  className={consoleLayout.refreshBtn}
                >
                  刷新橋接狀態
                </button>
              </div>

              <div className="mb-3 flex flex-wrap gap-3 text-[10px] text-[var(--console-sub)]">
                <span>
                  MineMCP：
                  <span className="text-[var(--console-accent)]">
                    {bridgeStatus?.enabled ? (bridgeStatus.connected ? '已連線' : '未連線') : '未啟用（乾跑）'}
                  </span>
                </span>
                {worldApplyResult && (
                  <span>
                    上次：
                    <span className="text-[var(--console-accent)]">{worldApplyResult.summary.overall_status}</span>
                  </span>
                )}
              </div>

              {worldPreview && worldPreview.length > 0 && (
                <ul className="mb-3 space-y-1 text-[10px] text-[var(--console-sub)]">
                  {worldPreview.map((row) => (
                    <li key={`${row.kind}-${row.id}`}>
                      {row.title} · {row.kind} @ ({row.spawn?.x ?? '?'}, {row.spawn?.y ?? '?'}, {row.spawn?.z ?? '?'})
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={worldBusy !== 'idle'}
                  onClick={() => void onPreviewWorld()}
                  className="rounded-lg border border-[var(--console-cyan)]/40 bg-[var(--console-cyan)]/10 px-3 py-1.5 text-[12px] text-[var(--console-cyan)] disabled:opacity-40"
                >
                  {worldBusy === 'preview' ? '預覽中…' : '預覽／估算'}
                </button>
                <button
                  type="button"
                  disabled={worldBusy !== 'idle'}
                  onClick={() => void onApplyWorld()}
                  className="rounded-lg border border-[var(--console-accent)]/40 bg-[var(--console-accent)]/10 px-3 py-1.5 text-[12px] text-[var(--console-accent)] disabled:opacity-40"
                >
                  {worldBusy === 'apply' ? '落地中…' : '落地 NPC／任務／道具'}
                </button>
              </div>

              {bridgeStatus?.enabled && !bridgeStatus.connected && (
                <p className={`mt-2 ${consoleLayout.warnBar}`}>
                  橋接未連線：仍會更新 Linkin 世界資料並標記 partial；連線後可重試遊戲內生成。
                </p>
              )}
            </section>
          )}

          {committedBriefId && buildBrief && (
            <section className="rounded-xl border border-[#c9a961]/30 bg-[var(--console-card)] p-4">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="mc-kicker">落地建築</p>
                  <h3 className="text-[13px] font-medium text-[#c9a961]">{buildBrief.title}</h3>
                  <p className="mt-1 text-[11px] text-[#8a8f98]">
                    {buildBrief.id} · {buildBrief.region} · {buildBrief.location} · 狀態 {buildBrief.status ?? 'pending_builder'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void refreshBridgeStatus()}
                  className="rounded-lg border border-[#c9a961]/30 px-2 py-1 text-[10px] text-[#c9a961]"
                >
                  刷新橋接狀態
                </button>
              </div>

              <p className="mb-3 text-[11px] leading-relaxed text-[var(--console-sub)]">{buildBrief.prompt}</p>

              <div className="mb-3 flex flex-wrap gap-3 text-[10px] text-[#8a8f98]">
                <span>
                  MineMCP：
                  <span className="text-[#c9a961]">
                    {bridgeStatus?.enabled ? (bridgeStatus.connected ? '已連線' : '未連線') : '未啟用（乾跑）'}
                  </span>
                </span>
                {briefPreview && (
                  <span>
                    預估方塊：<span className="text-[#c9a961]">{briefPreview.bounds.solid_count}</span>
                  </span>
                )}
                {applyResult && (
                  <span>
                    已放置：<span className="text-[#c9a961]">{applyResult.placement.blocks_placed}</span>/
                    {applyResult.placement.blocks_total}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={buildBusy !== 'idle'}
                  onClick={() => void onPreviewBuild()}
                  className="rounded-lg border border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-3 py-1.5 text-[12px] text-[var(--console-accent)] disabled:opacity-40"
                >
                  {buildBusy === 'preview' ? '預覽中…' : '預覽／估算'}
                </button>
                <button
                  type="button"
                  disabled={buildBusy !== 'idle'}
                  onClick={() => void onApplyBuild()}
                  className="rounded-lg border border-[#c9a961]/40 bg-[#c9a961]/10 px-3 py-1.5 text-[12px] text-[#c9a961] disabled:opacity-40"
                >
                  {buildBusy === 'apply' ? '落地中…' : '落地建築'}
                </button>
              </div>

              {briefPreview?.bounds.world_max && (
                <p className="mt-3 text-[10px] text-[var(--console-sub)]">
                  世界邊界：({briefPreview.bounds.world_min?.x}, {briefPreview.bounds.world_min?.y},{' '}
                  {briefPreview.bounds.world_min?.z}) → ({briefPreview.bounds.world_max.x},{' '}
                  {briefPreview.bounds.world_max.y}, {briefPreview.bounds.world_max.z})
                </p>
              )}

              {bridgeStatus?.enabled && !bridgeStatus.connected && (
                <p className="mt-2 text-[11px] text-[var(--console-amber)]">
                  橋接未連線：落地建築將被拒絕。請在 Minecraft 橋接面板確認 Token 與伺服器後再試。
                </p>
              )}
            </section>
          )}
        </div>
      )}

      <section className="mt-4 rounded-xl border border-[color-mix(in_srgb,var(--console-accent)_20%,transparent)] bg-[var(--console-card)] p-3">
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="mc-kicker">區域地圖</p>
            <h3>先生成，預覽後再落地</h3>
            <p className="mc-note">
              用地圖草稿或已提交的內容產生區域地圖。預覽不會寫進世界，落地前會再確認一次。
            </p>
          </div>
        </div>

        <div className="mb-3 flex gap-1">
          {PHASE4_STEPS.map((step, idx) => {
            const done = idx < phase4Index;
            const active = step === mapStep;
            return (
              <div key={step} className="flex-1">
                <div
                  className={`h-1.5 w-full rounded-full ${
                    done ? 'bg-[#c9a961]' : active ? 'progress-shimmer bg-[color-mix(in_srgb,var(--console-accent)_60%,transparent)]' : 'bg-gray-700/70'
                  }`}
                />
                <p className={`mt-1 text-center text-[10px] ${active ? 'text-[var(--console-accent)]' : 'text-[var(--console-sub)]'}`}>
                  {PHASE4_LABELS[step]}
                </p>
              </div>
            );
          })}
        </div>

        {mapNote && (
          <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
            {mapNote}
          </div>
        )}

        <div className="grid gap-3 lg:grid-cols-2">
          <div className="space-y-2 rounded-lg border border-white/[0.06] bg-black/20 p-3">
            <label className="block text-[10px] text-[#8a8f98]">
              區域 seed（可選）
              <input
                value={mapSeed}
                onChange={(e) => {
                  setMapSeed(e.target.value);
                  setMapStep('brief');
                }}
                placeholder={theme || region}
                className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]"
              />
            </label>
            <p className="text-[10px] text-[var(--console-sub)]">
              來源：{workspace ? `工作區 ${workspace.workspace_id}` : '僅 region／已提交實體'} · 區域 {region}
            </p>
            <div className="flex flex-wrap gap-2 pt-1">
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setMapStep('generate');
                  void onGenerateMap();
                }}
                className="rounded-lg border border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] px-3 py-1.5 text-[12px] text-[var(--console-accent)] disabled:opacity-40"
              >
                生成地圖
              </button>
              <button
                type="button"
                disabled={busy || !mapPlan}
                onClick={() => void onRefreshMapPreview()}
                className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[var(--console-sub)] disabled:opacity-40"
              >
                重新預覽
              </button>
              <button
                type="button"
                disabled={busy || !mapPlan}
                onClick={() => {
                  setMapStep('apply');
                  void onApplyMap();
                }}
                className="rounded-lg border border-[#c9a961]/40 bg-[#c9a961]/10 px-3 py-1.5 text-[12px] text-[#c9a961] disabled:opacity-40"
              >
                落地地圖（confirm）
              </button>
            </div>
          </div>

          <div className="min-h-[180px] rounded-lg border border-white/[0.06] bg-[var(--console-bg)] p-3">
            {mapPreview ? (
              <div className="space-y-2 text-[11px]">
                <p className="font-medium text-[var(--console-ink)]">{mapPreview.title}</p>
                <p className="text-[#8a8f98]">
                  plots {mapPreview.plot_count} · 預估 {mapPreview.estimated_blocks} 方塊 · 跨度 x
                  {mapPreview.axis_span.x}/y{mapPreview.axis_span.y}/z{mapPreview.axis_span.z}
                </p>
                <p className="text-[10px] text-[var(--console-sub)]">
                  bounds ({mapPreview.bounds.x1},{mapPreview.bounds.y1},{mapPreview.bounds.z1}) → (
                  {mapPreview.bounds.x2},{mapPreview.bounds.y2},{mapPreview.bounds.z2})
                </p>
                <div>
                  <p className="mb-1 text-[10px] uppercase text-[color-mix(in_srgb,var(--console-accent)_70%,transparent)]">POI</p>
                  <ul className="max-h-[120px] space-y-1 overflow-y-auto font-mono text-[10px] text-[var(--console-sub)]">
                    {mapPreview.pois.map((poi) => (
                      <li key={poi.id}>
                        {poi.title} · {poi.location} · {poi.kind}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-[var(--console-sub)]">尚未生成地圖。請設定 seed 後按「生成地圖」。</p>
            )}
          </div>
        </div>
      </section>
      </div>
    </McPage>
  );
}
