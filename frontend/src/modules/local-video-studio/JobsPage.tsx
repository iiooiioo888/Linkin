import { useCallback, useEffect, useState } from 'react';
import {
  cancelLvsJob,
  createLvsJob,
  getLvsJobLog,
  listLvsJobs,
  listLvsShots,
  recalledLvsProjectId,
  retryLvsJob,
  type LvsJob,
  type LvsJobLog,
  type LvsShot,
} from '../../lib/localVideoStudioApi';
import { StatusBadge, goLvs } from './ui';

export default function JobsPage() {
  const projectId = recalledLvsProjectId();
  const [jobs, setJobs] = useState<LvsJob[]>([]);
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [shotId, setShotId] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [logPreview, setLogPreview] = useState<LvsJobLog | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setError('');
    const [jobRows, shotRows] = await Promise.all([listLvsJobs(projectId), listLvsShots(projectId)]);
    setJobs(jobRows);
    setShots(shotRows);
    if (!shotId && shotRows[0]) setShotId(shotRows[0].id);
  }, [projectId, shotId]);

  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [refresh]);

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

  const onCancel = async (jobId: string) => {
    try {
      await cancelLvsJob(jobId);
      setMessage(`已取消 ${jobId.slice(0, 8)}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const onRetry = async (jobId: string) => {
    try {
      await retryLvsJob(jobId);
      setMessage(`已重試 ${jobId.slice(0, 8)}`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const onShowLog = async (jobId: string) => {
    setError('');
    try {
      const log = await getLvsJobLog(jobId);
      setLogPreview(log);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-jobs">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">任務</h2>
          <p className="text-[12px] text-[var(--console-sub)]">狀態 · attempt · 錯誤 · 取消／重試</p>
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
                seed: 7,
                frames: 121,
                output_relative_path: `projects/${projectId}/drafts/${shotId}.mp4`,
                input_image_relative_path: `projects/${projectId}/keyframes/${shotId}.png`,
              })
            }
            data-testid="lvs-job-create-draft"
          >
            草稿
          </button>
          <button
            type="button"
            className="rounded border border-[var(--console-line)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
            onClick={() =>
              void enqueue('refine', 'wan5b_refine', {
                prompt: 'refined cinematic clip',
                seed: 11,
                frames: 121,
                output_relative_path: `projects/${projectId}/refines/${shotId}.mp4`,
                input_image_relative_path: `projects/${projectId}/keyframes/${shotId}.png`,
              })
            }
            data-testid="lvs-job-create-refine"
          >
            精修
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => goLvs('shots')}>
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
            <th className="py-2 pr-2 font-medium">Attempt</th>
            <th className="py-2 pr-2 font-medium">Agent</th>
            <th className="py-2 pr-2 font-medium">資產／錯誤</th>
            <th className="py-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id} className="border-b border-[var(--console-line)] text-[var(--console-ink)]">
              <td className="py-2 pr-2 font-mono">{job.id.slice(0, 8)}</td>
              <td className="py-2 pr-2">
                {job.job_type}/{job.workflow_template}
              </td>
              <td className="py-2 pr-2">
                <StatusBadge status={job.status} />
              </td>
              <td className="py-2 pr-2 font-mono">
                {job.attempt}/{job.max_attempts}
              </td>
              <td className="py-2 pr-2">{job.assigned_agent || '—'}</td>
              <td className="py-2 pr-2 font-mono text-[11px] text-[var(--console-sub)]">
                {job.status === 'failed' ? (
                  <span className="text-red-400" data-testid="lvs-job-error-summary">
                    {job.error_summary || job.error || '失敗（無摘要）'}
                  </span>
                ) : (
                  job.asset?.relative_path || '—'
                )}
              </td>
              <td className="py-2">
                <div className="flex flex-wrap gap-2">
                  {(job.status === 'queued' || job.status === 'running') && (
                    <button
                      type="button"
                      className="text-red-400 hover:underline"
                      onClick={() => void onCancel(job.id)}
                    >
                      取消
                    </button>
                  )}
                  {(job.status === 'failed' || job.status === 'cancelled') && (
                    <button
                      type="button"
                      className="text-[var(--console-accent)] hover:underline"
                      onClick={() => void onRetry(job.id)}
                    >
                      重試
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-[var(--console-sub)] hover:underline"
                    onClick={() => void onShowLog(job.id)}
                    data-testid="lvs-job-log-btn"
                  >
                    日誌
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {jobs.length === 0 ? (
            <tr>
              <td colSpan={7} className="py-8 text-center text-[var(--console-sub)]">
                尚無任務
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>

      {logPreview ? (
        <section
          className="rounded border border-[var(--console-line)] p-3"
          data-testid="lvs-job-log-panel"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-[13px] font-medium text-[var(--console-ink)]">
              日誌 · {logPreview.job_id.slice(0, 8)}
            </h3>
            <button
              type="button"
              className="text-[12px] text-[var(--console-sub)] hover:underline"
              onClick={() => setLogPreview(null)}
            >
              關閉
            </button>
          </div>
          <p className="mb-2 font-mono text-[11px] text-[var(--console-sub)]">
            {logPreview.log_relative_path}
            {logPreview.error_summary ? (
              <>
                {' · '}
                <span className="text-red-400">{logPreview.error_summary}</span>
              </>
            ) : null}
          </p>
          <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-[var(--console-ink)]">
            {logPreview.exists ? logPreview.content || '（空）' : '（尚未產生日誌檔）'}
          </pre>
        </section>
      ) : null}
    </div>
  );
}
