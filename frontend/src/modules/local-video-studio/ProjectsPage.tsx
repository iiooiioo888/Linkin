import { useCallback, useEffect, useState } from 'react';
import {
  createLvsProject,
  listLvsProjects,
  rememberLvsProjectId,
  type LvsProject,
} from '../../lib/localVideoStudioApi';

function go(page: string): void {
  window.location.hash = `#/modules/local-video-studio/${page}`;
}

export default function ProjectsPage() {
  const [items, setItems] = useState<LvsProject[]>([]);
  const [name, setName] = useState('demo');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setItems(await listLvsProjects());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onCreate = async () => {
    setError('');
    try {
      const project = await createLvsProject({
        name: name.trim() || 'untitled',
        description: description.trim() || undefined,
      });
      rememberLvsProjectId(project.id);
      setName('demo');
      setDescription('');
      await refresh();
      go('detail');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-projects">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">專案</h2>
          <p className="text-[12px] text-[var(--console-sub)]">M1：建立專案後可匯入鏡頭表</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[11px] text-[var(--console-sub)]">
            名稱
            <input
              className="rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px] text-[var(--console-ink)]"
              value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="lvs-project-name"
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-[var(--console-sub)]">
            說明
            <input
              className="min-w-[12rem] rounded border border-[var(--console-line)] bg-transparent px-2 py-1 text-[12px] text-[var(--console-ink)]"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="lvs-project-desc"
            />
          </label>
          <button
            type="button"
            className="rounded bg-[var(--console-accent)] px-3 py-1.5 text-[12px] text-white"
            onClick={() => void onCreate()}
            data-testid="lvs-project-create"
          >
            建立
          </button>
        </div>
      </header>

      {error ? (
        <p className="text-[12px] text-red-400" data-testid="lvs-projects-error">
          {error}
        </p>
      ) : null}
      {loading ? <p className="text-[12px] text-[var(--console-sub)]">載入中…</p> : null}

      <ul className="divide-y divide-[var(--console-line)] border-t border-[var(--console-line)]">
        {items.map((item) => (
          <li key={item.id} className="flex items-center justify-between gap-3 py-3">
            <div>
              <p className="text-[13px] font-medium text-[var(--console-ink)]">{item.name}</p>
              <p className="text-[11px] text-[var(--console-sub)]">
                {item.status} · {item.shot_count} 鏡頭 · {item.id.slice(0, 8)}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="text-[12px] text-[var(--console-accent)] hover:underline"
                onClick={() => {
                  rememberLvsProjectId(item.id);
                  go('detail');
                }}
              >
                詳情
              </button>
              <button
                type="button"
                className="text-[12px] text-[var(--console-accent)] hover:underline"
                onClick={() => {
                  rememberLvsProjectId(item.id);
                  go('shots');
                }}
                data-testid={`lvs-open-shots-${item.id}`}
              >
                鏡頭板
              </button>
            </div>
          </li>
        ))}
        {!loading && items.length === 0 ? (
          <li className="py-8 text-center text-[12px] text-[var(--console-sub)]">尚無專案</li>
        ) : null}
      </ul>
    </div>
  );
}
