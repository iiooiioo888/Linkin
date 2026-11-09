import { useCallback, useEffect, useState } from 'react';
import {
  composeLvsProject,
  listLvsShots,
  recalledLvsProjectId,
  type LvsShot,
} from '../../lib/localVideoStudioApi';

function go(page: string): void {
  window.location.hash = `#/modules/local-video-studio/${page}`;
}

export default function ComposePanel() {
  const projectId = recalledLvsProjectId();
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState('');
  const [result, setResult] = useState('');

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const rows = await listLvsShots(projectId);
    setShots(rows);
    setSelected(rows.filter((s) => s.status === 'approved').map((s) => s.id));
  }, [projectId]);

  useEffect(() => {
    void refresh().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [refresh]);

  if (!projectId) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-[12px] text-[var(--console-sub)]">
        尚未選擇專案
      </div>
    );
  }

  const toggle = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const onCompose = async () => {
    setError('');
    setResult('');
    try {
      const out = await composeLvsProject(projectId, {
        shot_ids: selected,
        add_watermark: true,
        output_name: 'final_v1.mp4',
      });
      setResult(`${out.relative_path} · compliance ${out.compliance_id.slice(0, 8)} · ${out.engine}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-compose">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">合成</h2>
          <p className="text-[12px] text-[var(--console-sub)]">僅 approved 鏡頭；成功前強制合規 stamp（M5）</p>
        </div>
        <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => go('review')}>
          審核
        </button>
      </header>
      <ul className="space-y-2 text-[12px]">
        {shots.map((shot) => (
          <li key={shot.id} className="flex items-center gap-2 text-[var(--console-ink)]">
            <input
              type="checkbox"
              checked={selected.includes(shot.id)}
              disabled={shot.status !== 'approved'}
              onChange={() => toggle(shot.id)}
            />
            <span>
              {shot.scene_no}/{shot.shot_no} · {shot.status} · {shot.description}
            </span>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="w-fit rounded bg-[var(--console-accent)] px-3 py-1.5 text-[12px] text-white disabled:opacity-40"
        disabled={selected.length === 0}
        onClick={() => void onCompose()}
        data-testid="lvs-compose-run"
      >
        生成成片
      </button>
      {result ? <p className="font-mono text-[11px] text-[var(--console-accent)]">{result}</p> : null}
      {error ? <p className="text-[12px] text-red-400">{error}</p> : null}
    </div>
  );
}
