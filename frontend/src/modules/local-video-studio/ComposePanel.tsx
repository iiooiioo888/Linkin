import { useCallback, useEffect, useState } from 'react';
import {
  composeLvsProjectFull,
  getLvsCompliance,
  listLvsAssets,
  listLvsShots,
  lvsAssetMediaUrl,
  recalledLvsProjectId,
  uploadLvsFile,
  type LvsAsset,
  type LvsShot,
} from '../../lib/localVideoStudioApi';
import { StatusBadge, goLvs } from './ui';

export default function ComposePanel() {
  const projectId = recalledLvsProjectId();
  const [shots, setShots] = useState<LvsShot[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [audioPath, setAudioPath] = useState('');
  const [subtitlePath, setSubtitlePath] = useState('');
  const [error, setError] = useState('');
  const [result, setResult] = useState('');
  const [finalAsset, setFinalAsset] = useState<LvsAsset | null>(null);
  const [compliance, setCompliance] = useState<string>('');

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const rows = await listLvsShots(projectId);
    setShots(rows);
    setSelected((prev) => {
      const approved = rows.filter((s) => s.status === 'approved').map((s) => s.id);
      if (prev.length === 0) return approved;
      return prev.filter((id) => approved.includes(id)).concat(approved.filter((id) => !prev.includes(id)));
    });
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

  const move = (id: string, dir: -1 | 1) => {
    setSelected((prev) => {
      const idx = prev.indexOf(id);
      if (idx < 0) return prev;
      const next = [...prev];
      const j = idx + dir;
      if (j < 0 || j >= next.length) return prev;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };

  const toggle = (id: string) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const onUpload = async (kind: 'audio' | 'subtitle', file: File | null) => {
    if (!file) return;
    setError('');
    try {
      const out = await uploadLvsFile(projectId, kind, file);
      if (kind === 'audio') setAudioPath(out.relative_path);
      else setSubtitlePath(out.relative_path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const onCompose = async () => {
    setError('');
    setResult('');
    setCompliance('');
    setFinalAsset(null);
    try {
      const out = await composeLvsProjectFull(projectId, {
        shot_ids: selected,
        add_watermark: true,
        output_name: 'final_v1.mp4',
        metadata: {
          audio_relative_path: audioPath || undefined,
          subtitle_relative_path: subtitlePath || undefined,
        },
      });
      setResult(`${out.relative_path} · ${out.engine}`);
      setFinalAsset(out.asset);
      const stamp = await getLvsCompliance(out.asset.id);
      setCompliance(
        `compliance ${stamp.id.slice(0, 8)} · mark=${stamp.explicit_mark} · ${stamp.watermark_id || ''}`,
      );
      const finals = await listLvsAssets(projectId, 'final');
      if (finals[0]) setFinalAsset(finals[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const approved = shots.filter((s) => s.status === 'approved');

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" data-testid="lvs-compose">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-[16px] font-semibold text-[var(--console-ink)]">合成</h2>
          <p className="text-[12px] text-[var(--console-sub)]">
            已通過鏡頭排序 · 音訊／字幕 · 強制合規 stamp
          </p>
        </div>
        <button type="button" className="text-[12px] text-[var(--console-accent)] hover:underline" onClick={() => goLvs('review')}>
          審核
        </button>
      </header>

      <ul className="space-y-2 text-[12px]" data-testid="lvs-compose-shots">
        {approved.map((shot) => {
          const checked = selected.includes(shot.id);
          const order = selected.indexOf(shot.id);
          return (
            <li key={shot.id} className="flex flex-wrap items-center gap-2 text-[var(--console-ink)]">
              <input type="checkbox" checked={checked} onChange={() => toggle(shot.id)} />
              <StatusBadge status={shot.status} />
              <span>
                {shot.scene_no}/{shot.shot_no} · {shot.description}
              </span>
              {checked ? (
                <span className="flex items-center gap-1 font-mono text-[11px] text-[var(--console-sub)]">
                  #{order + 1}
                  <button type="button" className="hover:underline" onClick={() => move(shot.id, -1)}>
                    ↑
                  </button>
                  <button type="button" className="hover:underline" onClick={() => move(shot.id, 1)}>
                    ↓
                  </button>
                </span>
              ) : null}
            </li>
          );
        })}
        {approved.length === 0 ? (
          <li className="text-[var(--console-sub)]">尚無 approved 鏡頭 — 請先至審核頁通過</li>
        ) : null}
      </ul>

      <div className="flex flex-wrap gap-4 text-[12px]">
        <label className="flex flex-col gap-1 text-[var(--console-sub)]">
          音訊
          <input
            type="file"
            accept="audio/*,.wav,.mp3"
            onChange={(e) => void onUpload('audio', e.target.files?.[0] || null)}
            data-testid="lvs-compose-audio"
          />
          {audioPath ? <span className="font-mono text-[10px]">{audioPath}</span> : null}
        </label>
        <label className="flex flex-col gap-1 text-[var(--console-sub)]">
          字幕
          <input
            type="file"
            accept=".srt,.vtt,text/*"
            onChange={(e) => void onUpload('subtitle', e.target.files?.[0] || null)}
            data-testid="lvs-compose-subtitle"
          />
          {subtitlePath ? <span className="font-mono text-[10px]">{subtitlePath}</span> : null}
        </label>
      </div>

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
      {compliance ? (
        <p className="font-mono text-[11px] text-[var(--console-ink)]" data-testid="lvs-compose-compliance">
          {compliance}
        </p>
      ) : null}
      {finalAsset ? (
        <video
          src={lvsAssetMediaUrl(finalAsset.id)}
          controls
          className="max-h-64 w-full max-w-xl bg-black"
          data-testid="lvs-compose-player"
        />
      ) : null}
      {error ? <p className="text-[12px] text-red-400">{error}</p> : null}
    </div>
  );
}
