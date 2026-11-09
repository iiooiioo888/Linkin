import { useCallback, useEffect, useState } from 'react';
import {
  createLvsJob,
  listLvsJobs,
  listLvsShots,
  recalledLvsProjectId,
  type LvsJob,
  type LvsShot,
} from '../../lib/localVideoStudioApi';

function go(page: string): void {
  window.location.hash = `#/modules/local-video-studio/${page}`;
}

export default function JobsPage() {
  const projectId = recalledLvsProjectId();
  const [jobs, setJobs] = useState<LvsJob[]>([]);
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [shotId, setShotId] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setError('');
    try {
      const [jobRows, shotRows] = await Promise.all([
        listLvsJobs(projectId),
        listLvsShots(projectId),
      ]);
      setJobs(jobRows);
      setShots(shotRows);
      if (!shotId && shotRows[0]) setShotId(shotRows[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [projectId, shotId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (!projectId) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-[12px] text-[var(--console-sub)]">
        尚未選擇專案。
        <button type="button" className="ml-2 text-[var(--console-accent)] hover:underline" onClick={() => go('projects')}>
          回專案列表
        </button>
      </div>
    );
  }

  const enqueue = async (
    job_type: 'keyframe' | 'draft' | 'refine',
    workflow_template: string,
    params: Record<string, unknown>,
  ) => {
    setMessage('');
    setError('');
    if (!shotId) {
      setError('請先選擇鏡頭');
      return;
    }
    try {
      const job = await createLvsJob({
        project_id: projectId,
        shot_id: shotId,
        job_type,
        workflow_template,
        params,
      });
      setMessage(`已建立 ${job_type} ${job.id.slice(0, 8)}（queued）`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-jobs">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">任務</h2>
          <p className="text-[12px] text-[var(--console-sub)]">
            keyframe／ltx_draft／wan5b_refine → agent（mock 或真實 ComfyUI）
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[11px] text-[var(--console-sub)]">
            鏡頭
            <select
              className="rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px] text-[var(--console-ink)]"
              value={shotId}
              onChange={(e) => setShotId(e.target.value)}
              data-testid="lvs-job-shot"
            >
              {shots.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.scene_no}/{s.shot_no} — {s.description.slice(0, 32)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="rounded bg-[var(--console-accent)] px-3 py-1.5 text-[12px] text-white"
            onClick={() =>
              void enqueue('keyframe', 'keyframe_flux_ipadapter', {
                prompt: 'cinematic keyframe',
                negative_prompt: 'blurry',
                seed: 42,
                width: 1024,
                height: 1024,
                input_image_relative_path: `projects/${projectId}/script/ref.png`,
                output_relative_path: `projects/${projectId}/keyframes/${shotId}.png`,
              })
            }
            data-testid="lvs-job-create-keyframe"
          >
            關鍵幀
          </button>
          <button
            type="button"
            className="rounded border border-[var(--console-line)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
            onClick={() =>
              void enqueue('draft', 'ltx_draft', {
                prompt: 'cinematic draft clip',
                negative_prompt: 'blurry',
                seed: 7,
                width: 1280,
                height: 704,
                frames: 121,
                input_image_relative_path: `projects/${projectId}/keyframes/${shotId}.png`,
                output_relative_path: `projects/${projectId}/drafts/${shotId}.mp4`,
              })
            }
            data-testid="lvs-job-create-draft"
          >
            草稿 LTX
          </button>
          <button
            type="button"
            className="rounded border border-[var(--console-line)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
            onClick={() =>
              void enqueue('refine', 'wan5b_refine', {
                prompt: 'refined cinematic clip',
                negative_prompt: 'artifacts',
                seed: 11,
                width: 1280,
                height: 704,
                frames: 121,
                input_image_relative_path: `projects/${projectId}/keyframes/${shotId}.png`,
                output_relative_path: `projects/${projectId}/refines/${shotId}.mp4`,
              })
            }
            data-testid="lvs-job-create-refine"
          >
            精修 Wan5B
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => go('review')}>
            審核
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => go('shots')}>
            鏡頭板
          </button>
        </div>
      </header>

      {message ? <p className="text-[12px] text-[var(--console-accent)]">{message}</p> : null}
      {error ? (
        <p className="text-[12px] text-red-400" data-testid="lvs-jobs-error">
          {error}
        </p>
      ) : null}

      <table className="w-full border-collapse text-left text-[12px]" data-testid="lvs-job-table">
        <thead>
          <tr className="border-b border-[var(--console-line)] text-[var(--console-sub)]">
            <th className="py-2 pr-2 font-medium">ID</th>
            <th className="py-2 pr-2 font-medium">類型</th>
            <th className="py-2 pr-2 font-medium">狀態</th>
            <th className="py-2 pr-2 font-medium">Agent</th>
            <th className="py-2 font-medium">資產</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-b border-[var(--console-line)] text-[var(--console-ink)]">
              <td className="py-2 pr-2 font-mono">{job.id.slice(0, 8)}</td>
              <td className="py-2 pr-2">
                {job.job_type}/{job.workflow_template}
              </td>
              <td className="py-2 pr-2">{job.status}</td>
              <td className="py-2 pr-2">{job.assigned_agent || '—'}</td>
              <td className="py-2 font-mono text-[11px] text-[var(--console-sub)]">
                {job.asset?.relative_path || job.error || '—'}
              </td>
            </tr>
          ))}
          {jobs.length === 0 ? (
            <tr>
              <td colSpan={5} className="py-8 text-center text-[var(--console-sub)]">
                尚無任務
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
