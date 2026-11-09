import { useEffect, useState } from 'react';
import { getLvsProject, recalledLvsProjectId, type LvsProject } from '../../lib/localVideoStudioApi';

function go(page: string): void {
  window.location.hash = `#/modules/local-video-studio/${page}`;
}

export default function ProjectDetailPage() {
  const [project, setProject] = useState<LvsProject | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const id = recalledLvsProjectId();
    if (!id) {
      setError('尚未選擇專案，請先從專案列表進入。');
      return;
    }
    void getLvsProject(id)
      .then(setProject)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-detail">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">專案詳情</h2>
          <p className="text-[12px] text-[var(--console-sub)]">狀態與鏡頭統計（M1 唯讀＋導覽）</p>
        </div>
        <div className="flex gap-3 text-[12px]">
          <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => go('projects')}>
            專案列表
          </button>
          <button type="button" className="text-[var(--console-accent)] hover:underline" onClick={() => go('shots')}>
            鏡頭板
          </button>
        </div>
      </header>

      {error ? (
        <p className="text-[12px] text-red-400" data-testid="lvs-detail-error">
          {error}
        </p>
      ) : null}

      {project ? (
        <dl className="grid max-w-lg grid-cols-[7rem_1fr] gap-x-3 gap-y-2 text-[12px]" data-testid="lvs-detail-card">
          <dt className="text-[var(--console-sub)]">名稱</dt>
          <dd className="text-[var(--console-ink)]">{project.name}</dd>
          <dt className="text-[var(--console-sub)]">狀態</dt>
          <dd className="text-[var(--console-ink)]">{project.status}</dd>
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
    </div>
  );
}
