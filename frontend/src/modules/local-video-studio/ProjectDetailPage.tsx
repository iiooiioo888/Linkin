import { useCallback, useEffect, useState } from 'react';
import {
  getLvsProject,
  getLvsResources,
  listLvsShots,
  recalledLvsProjectId,
  uploadLvsScript,
  type LvsProject,
  type LvsResourceSummary,
  type LvsShot,
} from '../../lib/localVideoStudioApi';
import { StatusBadge, formatBytes, goLvs } from './ui';

const DEMO_SCRIPT = {
  project_title: 'demo',
  shots: [
    { scene_no: 1, shot_no: 1, description: 'wide rainy alley', duration_sec: 5 },
    { scene_no: 1, shot_no: 2, description: 'close-up look up', duration_sec: 4 },
    { scene_no: 2, shot_no: 1, description: 'drone dusk', duration_sec: 6 },
  ],
};

export default function ProjectDetailPage() {
  const [project, setProject] = useState<LvsProject | null>(null);
  const [resources, setResources] = useState<LvsResourceSummary | null>(null);
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const projectId = recalledLvsProjectId();

  const refresh = useCallback(async () => {
    if (!projectId) {
      setError('尚未選擇專案，請先從專案列表進入。');
      return;
    }
    const [p, r, s] = await Promise.all([
      getLvsProject(projectId),
      getLvsResources(projectId),
      listLvsShots(projectId),
    ]);
    setProject(p);
    setResources(r);
    setShots(s);
    setError('');
  }, [projectId]);

  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [refresh]);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-detail">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">專案詳情</h2>
          <p className="text-[12px] text-[var(--console-sub)]">概覽 · 鏡頭表 · 資源消耗</p>
        </div>
        <div className="flex flex-wrap gap-3 text-[12px]">
          <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => goLvs('projects')}>
            專案
          </button>
          <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => goLvs('shots')}>
            鏡頭板
          </button>
          <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => goLvs('resources')}>
            資源
          </button>
          <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => goLvs('compose')}>
            合成
          </button>
        </div>
      </header>

      {error ? (
        <p className="text-[12px] text-red-400" data-testid="lvs-detail-error">
          {error}
        </p>
      ) : null}
      {message ? <p className="text-[12px] text-[var(--console-accent)]">{message}</p> : null}

      {project ? (
        <dl className="grid max-w-lg grid-cols-[7rem_1fr] gap-x-3 gap-y-2 text-[12px]" data-testid="lvs-detail-card">
          <dt className="text-[var(--console-sub)]">名稱</dt>
          <dd className="text-[var(--console-ink)]">{project.name}</dd>
          <dt className="text-[var(--console-sub)]">狀態</dt>
          <dd>
            <StatusBadge status={project.status} />
          </dd>
          <dt className="text-[var(--console-sub)]">鏡頭數</dt>
          <dd className="text-[var(--console-ink)]">{project.shot_count}</dd>
          <dt className="text-[var(--console-sub)]">說明</dt>
          <dd className="text-[var(--console-ink)]">{project.description || '—'}</dd>
          <dt className="text-[var(--console-sub)]">ID</dt>
          <dd className="font-mono text-[11px] text-[var(--console-sub)]">{project.id}</dd>
        </dl>
      ) : !error ? (
        <p className="text-[12px] text-[var(--console-sub)]">載入中…</p>
      ) : null}

      {projectId ? (
        <div>
          <button
            type="button"
            className="rounded border border-[var(--console-line)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
            onClick={() =>
              void uploadLvsScript(projectId, DEMO_SCRIPT)
                .then(async (r) => {
                  setMessage(`鏡頭表 v${r.version}，寫入 ${r.imported_shots} 鏡`);
                  await refresh();
                })
                .catch((err) => setError(err instanceof Error ? err.message : String(err)))
            }
            data-testid="lvs-detail-import"
          >
            上傳示範鏡頭表
          </button>
        </div>
      ) : null}

      <section>
        <h3 className="mb-2 text-[13px] font-medium text-[var(--console-ink)]">鏡頭列表</h3>
        <ul className="divide-y divide-[var(--console-line)] text-[12px]">
          {shots.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-3 py-2 text-[var(--console-ink)]">
              <span>
                {s.scene_no}/{s.shot_no} · {s.description}
              </span>
              <StatusBadge status={s.status} />
            </li>
          ))}
          {shots.length === 0 ? (
            <li className="py-4 text-[var(--console-sub)]">尚無鏡頭</li>
          ) : null}
        </ul>
      </section>

      {resources ? (
        <section data-testid="lvs-resources">
          <h3 className="mb-2 text-[13px] font-medium text-[var(--console-ink)]">資源消耗摘要</h3>
          <dl className="grid max-w-lg grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-[12px]">
            <dt className="text-[var(--console-sub)]">GPU 分鐘</dt>
            <dd className="text-[var(--console-ink)]">{resources.gpu_minutes}</dd>
            <dt className="text-[var(--console-sub)]">儲存</dt>
            <dd className="text-[var(--console-ink)]">{formatBytes(resources.storage_bytes)}</dd>
            <dt className="text-[var(--console-sub)]">任務／資產</dt>
            <dd className="text-[var(--console-ink)]">
              {resources.job_count} / {resources.asset_count}
            </dd>
          </dl>
        </section>
      ) : null}
    </div>
  );
}
