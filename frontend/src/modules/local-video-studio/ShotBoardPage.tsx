import { useCallback, useEffect, useState } from 'react';
import {
  createLvsShot,
  listLvsShots,
  recalledLvsProjectId,
  uploadLvsScript,
  type LvsShot,
} from '../../lib/localVideoStudioApi';

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

function go(page: string): void {
  window.location.hash = `#/modules/local-video-studio/${page}`;
}

export default function ShotBoardPage() {
  const projectId = recalledLvsProjectId();
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [desc, setDesc] = useState('');
  const [sceneNo, setSceneNo] = useState(1);
  const [shotNo, setShotNo] = useState(1);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    setError('');
    try {
      setShots(await listLvsShots(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [projectId]);

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

  const onImport = async () => {
    setMessage('');
    setError('');
    try {
      const result = await uploadLvsScript(projectId, DEMO_SCRIPT);
      setMessage(`已匯入鏡頭表 v${result.version}，寫入 ${result.imported_shots} 鏡`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const onCreate = async () => {
    setMessage('');
    setError('');
    try {
      await createLvsShot(projectId, {
        scene_no: sceneNo,
        shot_no: shotNo,
        description: desc.trim() || 'untitled shot',
      });
      setDesc('');
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-shots">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">鏡頭板</h2>
          <p className="font-mono text-[11px] text-[var(--console-sub)]">{projectId}</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-[var(--console-line)] px-3 py-1.5 text-[12px] text-[var(--console-ink)]"
            onClick={() => void onImport()}
            data-testid="lvs-import-script"
          >
            匯入示範 3 鏡
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => go('detail')}>
            詳情
          </button>
          <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => go('projects')}>
            專案
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
          onClick={() => void onCreate()}
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

      <table className="w-full border-collapse text-left text-[12px]" data-testid="lvs-shot-table">
        <thead>
          <tr className="border-b border-[var(--console-line)] text-[var(--console-sub)]">
            <th className="py-2 pr-2 font-medium">S/C</th>
            <th className="py-2 pr-2 font-medium">描述</th>
            <th className="py-2 pr-2 font-medium">秒數</th>
            <th className="py-2 font-medium">狀態</th>
          </tr>
        </thead>
        <tbody>
          {shots.map((shot) => (
            <tr key={shot.id} className="border-b border-[var(--console-line)] text-[var(--console-ink)]">
              <td className="py-2 pr-2 font-mono">
                {shot.scene_no}/{shot.shot_no}
              </td>
              <td className="py-2 pr-2">{shot.description}</td>
              <td className="py-2 pr-2">{shot.duration_sec}</td>
              <td className="py-2">{shot.status}</td>
            </tr>
          ))}
          {shots.length === 0 ? (
            <tr>
              <td colSpan={4} className="py-8 text-center text-[var(--console-sub)]">
                尚無鏡頭 — 可匯入示範 3 鏡
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
