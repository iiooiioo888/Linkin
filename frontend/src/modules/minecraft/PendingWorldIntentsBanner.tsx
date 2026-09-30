/**
 * 敘事工作區 commit 後待落地的 NPC／任務／道具提示條。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  applyWorldIntents,
  fetchPendingWorldIntents,
  previewWorldIntents,
  type PendingWorldIntents,
  type WorldIntentApplyResult,
} from '../../api/linkin';
import { statusLabel } from './monitor/shared';
import './minecraft.css';

type Props = {
  kind?: 'npc' | 'quest' | 'item';
  compact?: boolean;
};

export default function PendingWorldIntentsBanner({ kind, compact = false }: Props) {
  const [pending, setPending] = useState<PendingWorldIntents | null>(null);
  const [applyResult, setApplyResult] = useState<WorldIntentApplyResult | null>(null);
  const [busy, setBusy] = useState<'idle' | 'preview' | 'apply'>('idle');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchPendingWorldIntents();
      setPending(data.pending);
    } catch {
      setPending(null);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!pending?.count) return null;

  const rows =
    kind === 'npc'
      ? pending.npcs
      : kind === 'quest'
        ? pending.quests
        : kind === 'item'
          ? pending.items
          : [...pending.npcs, ...pending.quests, ...pending.items];

  if (kind && rows.length === 0) return null;

  const count = kind ? rows.length : pending.count;

  const onPreview = async () => {
    setBusy('preview');
    setError(null);
    try {
      await previewWorldIntents({ apply_all: !kind });
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const onApply = async () => {
    setBusy('apply');
    setError(null);
    try {
      const body = kind
        ? {
            npc_ids: kind === 'npc' ? rows.map((r) => r.id) : undefined,
            quest_ids: kind === 'quest' ? rows.map((r) => r.id) : undefined,
            item_ids: kind === 'item' ? rows.map((r) => r.id) : undefined,
          }
        : { apply_all: true };
      const result = await applyWorldIntents(body);
      setApplyResult(result);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const label =
    kind === 'npc' ? 'NPC' : kind === 'quest' ? '任務' : kind === 'item' ? '道具' : '世界內容';

  return (
    <section className="mc-callout">
      <div className="mc-row__top">
        <div>
          <p className="mc-callout__title">{count} 筆{label}還沒進世界</p>
          <p className="mc-callout__body">提交草稿只會先記下來。要出現在遊戲裡，需在這裡落地。</p>
          {applyResult ? (
            <p className="mc-callout__body">
              上次：已落地 {applyResult.summary.applied}
              {applyResult.summary.partial ? `，部分 ${applyResult.summary.partial}` : ''}
            </p>
          ) : null}
        </div>
        <div className="mc-actions">
          <button type="button" disabled={busy !== 'idle'} onClick={() => void onPreview()} className="mc-btn">
            {busy === 'preview' ? '預覽中' : '預覽'}
          </button>
          <button type="button" disabled={busy !== 'idle'} onClick={() => void onApply()} className="mc-btn is-primary">
            {busy === 'apply' ? '落地中' : '落地'}
          </button>
        </div>
      </div>
      {error ? <p className="mc-error" style={{ marginTop: 8 }}>{error}</p> : null}
      {!compact && rows.length > 0 ? (
        <ul className="mc-list" style={{ marginTop: 10 }}>
          {rows.slice(0, 5).map((row) => (
            <li key={row.id} className="mc-row">
              <span className="mc-row__title">
                {(row as { title?: string; name?: string }).title ??
                  (row as { name?: string }).name ??
                  row.id}
              </span>
              <span className="mc-row__meta">{statusLabel(row.world_status || 'pending_world')}</span>
            </li>
          ))}
          {rows.length > 5 ? <li className="mc-note">還有 {rows.length - 5} 筆</li> : null}
        </ul>
      ) : null}
    </section>
  );
}
