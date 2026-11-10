import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  createLvsJob,
  createLvsShot,
  listLvsAssets,
  listLvsShots,
  recalledLvsProjectId,
  reviewLvsAsset,
  uploadLvsScript,
  lvsAssetMediaUrl,
  type LvsAsset,
  type LvsShot,
} from '../../lib/localVideoStudioApi';
import { StatusBadge, goLvs } from './ui';

const DEMO_SCRIPT = {
  project_title: 'demo',
  shots: [
    {
      scene_no: 1,
      shot_no: 1,
      description: 'wide shot, rainy alley, neon light',
      dialogue: '',
      duration_sec: 5,
    },
    {
      scene_no: 1,
      shot_no: 2,
      description: 'close-up, character looks up',
      dialogue: '開始了',
      duration_sec: 4,
    },
    {
      scene_no: 2,
      shot_no: 1,
      description: 'drone over rooftops at dusk',
      dialogue: '',
      duration_sec: 6,
    },
  ],
};

function latestAsset(
  assets: LvsAsset[],
  shotId: string,
  types: string[],
): LvsAsset | undefined {
  return assets.find((a) => a.shot_id === shotId && types.includes(a.type));
}

export default function ShotBoardPage() {
  const projectId = recalledLvsProjectId();
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [assets, setAssets] = useState<LvsAsset[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [desc, setDesc] = useState('');
  const [sceneNo, setSceneNo] = useState(1);
  const [shotNo, setShotNo] = useState(1);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setError('');
    const [shotRows, assetRows] = await Promise.all([
      listLvsShots(projectId),
      listLvsAssets(projectId),
    ]);
    setShots(shotRows);
    setAssets(assetRows);
  }, [projectId]);

  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [refresh]);

  const byScene = useMemo(() => {
    const map = new Map<number, LvsShot[]>();
    for (const shot of shots) {
      const list = map.get(shot.scene_no) || [];
      list.push(shot);
      map.set(shot.scene_no, list);
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  }, [shots]);

  if (!projectId) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-[12px] text-[var(--console-sub)]">
        尚未選擇專案。
        <button type="button" className="ml-2 text-[var(--console-accent)] hover:underline" onClick={() => goLvs('projects')}>
          回專案列表
        </button>
      </div>
    );
  }

  const enqueue = async (shot: LvsShot, job_type: 'keyframe' | 'draft' | 'refine') => {
    setBusy(shot.id);
    setMessage('');
    setError('');
    try {
      const templates = {
        keyframe: 'keyframe_flux_ipadapter',
        draft: 'ltx_draft',
        refine: 'wan5b_refine',
      } as const;
      const folders = { keyframe: 'keyframes', draft: 'drafts', refine: 'refines' } as const;
      const ext = job_type === 'keyframe' ? 'png' : 'mp4';
      await createLvsJob({
        project_id: projectId,
        shot_id: shot.id,
        job_type,
        workflow_template: templates[job_type],
        params: {
          prompt: shot.description,
          negative_prompt: 'blurry, artifacts',
          seed: 42,
          width: job_type === 'keyframe' ? 1024 : 1280,
          height: job_type === 'keyframe' ? 1024 : 704,
          frames: 121,
          input_image_relative_path:
            shot.selected_keyframe_asset_id
              ? `projects/${projectId}/keyframes/${shot.id}.png`
              : `projects/${projectId}/script/ref.png`,
          output_relative_path: `projects/${projectId}/${folders[job_type]}/${shot.id}.${ext}`,
        },
      });
      setMessage(`已佇列 ${job_type} · ${shot.scene_no}/${shot.shot_no}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  const decide = async (shot: LvsShot, decision: 'approve' | 'reject' | 'needs_retry') => {
    const clip =
      assets.find((a) => a.id === shot.selected_clip_asset_id) ||
      latestAsset(assets, shot.id, ['refine', 'draft']);
    if (!clip) {
      setError('此鏡頭尚無可審核影片資產');
      return;
    }
    setBusy(shot.id);
    setError('');
    try {
      await reviewLvsAsset(clip.id, { decision, reason: decision });
      setMessage(`${decision} · ${shot.scene_no}/${shot.shot_no}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-shots">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">鏡頭板</h2>
          <p className="text-[12px] text-[var(--console-sub)]">
            依 scene 分組 · 關鍵幀／草稿／精修／審核（SPEC §10）
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded border border-[var(--console-line)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
            onClick={() =>
              void uploadLvsScript(projectId, DEMO_SCRIPT)
                .then(async (r) => {
                  setMessage(`已匯入 v${r.version}，${r.imported_shots} 鏡`);
                  await refresh();
                })
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
            }
            data-testid="lvs-import-script"
          >
            匯入示範 3 鏡
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => goLvs('review')}>
            審核
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => goLvs('jobs')}>
            任務
          </button>
        </div>
      </header>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-[11px] text-[var(--console-sub)]">
          Scene
          <input
            type="number"
            className="w-16 rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px]"
            value={sceneNo}
            onChange={(e) => setSceneNo(Number(e.target.value))}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] text-[var(--console-sub)]">
          Shot
          <input
            type="number"
            className="w-16 rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px]"
            value={shotNo}
            onChange={(e) => setShotNo(Number(e.target.value))}
          />
        </label>
        <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-[11px] text-[var(--console-sub)]">
          描述
          <input
            className="rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px] text-[var(--console-ink)]"
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            data-testid="lvs-shot-desc"
          />
        </label>
        <button
          type="button"
          className="rounded bg-[var(--console-accent)] px-3 py-1.5 text-[12px] text-white"
          onClick={() =>
            void createLvsShot(projectId, {
              scene_no: sceneNo,
              shot_no: shotNo,
              description: desc.trim() || 'untitled shot',
            })
              .then(async () => {
                setDesc('');
                await refresh();
              })
              .catch((err) => setError(err instanceof Error ? err.message : String(err)))
          }
          data-testid="lvs-shot-create"
        >
          新增鏡頭
        </button>
      </div>

      {message ? <p className="text-[12px] text-[var(--console-accent)]">{message}</p> : null}
      {error ? (
        <p className="text-[12px] text-red-400" data-testid="lvs-shots-error">
          {error}
        </p>
      ) : null}

      <div className="flex flex-col gap-6" data-testid="lvs-shot-board">
        {byScene.map(([scene, rows]) => (
          <section key={scene}>
            <h3 className="mb-2 text-[13px] font-medium text-[var(--console-ink)]">Scene {scene}</h3>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {rows
                .slice()
                .sort((a, b) => a.shot_no - b.shot_no)
                .map((shot) => {
                  const keyframe =
                    assets.find((a) => a.id === shot.selected_keyframe_asset_id) ||
                    latestAsset(assets, shot.id, ['keyframe']);
                  const clip =
                    assets.find((a) => a.id === shot.selected_clip_asset_id) ||
                    latestAsset(assets, shot.id, ['refine', 'draft']);
                  const disabled = busy === shot.id;
                  return (
                    <article
                      key={shot.id}
                      className="border border-[var(--console-line)] p-3"
                      data-testid={`lvs-shot-card-${shot.id}`}
                    >
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <div>
                          <p className="font-mono text-[12px] text-[var(--console-ink)]">
                            {shot.scene_no}/{shot.shot_no}
                          </p>
                          <p className="text-[12px] text-[var(--console-sub)]">{shot.description}</p>
                        </div>
                        <StatusBadge status={shot.status} />
                      </div>

                      <div className="mb-3 grid grid-cols-2 gap-2">
                        <div className="bg-black/40">
                          {keyframe ? (
                            <img
                              src={lvsAssetMediaUrl(keyframe.id)}
                              alt="keyframe"
                              className="h-24 w-full object-cover"
                            />
                          ) : (
                            <div className="flex h-24 items-center justify-center text-[10px] text-[var(--console-sub)]">
                              無關鍵幀
                            </div>
                          )}
                        </div>
                        <div className="bg-black/40">
                          {clip ? (
                            <video
                              src={lvsAssetMediaUrl(clip.id)}
                              controls
                              className="h-24 w-full object-cover"
                              preload="metadata"
                            />
                          ) : (
                            <div className="flex h-24 items-center justify-center text-[10px] text-[var(--console-sub)]">
                              無草稿／精修
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2 text-[11px]">
                        <button
                          type="button"
                          disabled={disabled}
                          className="text-[var(--console-accent)] hover:underline disabled:opacity-40"
                          onClick={() => void enqueue(shot, 'keyframe')}
                        >
                          生成關鍵幀
                        </button>
                        <button
                          type="button"
                          disabled={disabled}
                          className="text-[var(--console-accent)] hover:underline disabled:opacity-40"
                          onClick={() => void enqueue(shot, 'draft')}
                        >
                          生成草稿
                        </button>
                        <button
                          type="button"
                          disabled={disabled}
                          className="text-[var(--console-accent)] hover:underline disabled:opacity-40"
                          onClick={() => void enqueue(shot, 'refine')}
                        >
                          生成精修
                        </button>
                        <button
                          type="button"
                          disabled={disabled}
                          className="text-emerald-400 hover:underline disabled:opacity-40"
                          onClick={() => void decide(shot, 'approve')}
                        >
                          通過
                        </button>
                        <button
                          type="button"
                          disabled={disabled}
                          className="text-red-400 hover:underline disabled:opacity-40"
                          onClick={() => void decide(shot, 'reject')}
                        >
                          駁回
                        </button>
                        <button
                          type="button"
                          disabled={disabled}
                          className="text-amber-300 hover:underline disabled:opacity-40"
                          onClick={() => void decide(shot, 'needs_retry')}
                        >
                          重試
                        </button>
                      </div>
                    </article>
                  );
                })}
            </div>
          </section>
        ))}
        {shots.length === 0 ? (
          <p className="py-8 text-center text-[12px] text-[var(--console-sub)]">尚無鏡頭 — 可匯入示範 3 鏡</p>
        ) : null}
      </div>
    </div>
  );
}
