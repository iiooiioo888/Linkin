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
import { consoleLayout } from '../../lib/consoleLayout';

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
    <section
      className={`${consoleLayout.insetCard} ${compact ? 'mb-3' : 'mb-4'} border-[var(--console-accent)]/30 bg-[var(--console-accent)]/5`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[10px] uppercase tracking-wide text-[var(--console-accent)]">
            Phase 3 · 敘事待落地
          </p>
          <p className="mt-1 text-[12px] text-[var(--console-ink)]">
            {count} 筆{label}意圖待套用至世界層（不會在 commit 時自動生成）
          </p>
          {applyResult && (
            <p className="mt-1 text-[10px] text-[var(--console-sub)]">
              上次結果：{applyResult.summary.overall_status} · 已套用 {applyResult.summary.applied} · 部分{' '}
              {applyResult.summary.partial}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={busy !== 'idle'}
            onClick={() => void onPreview()}
            className="rounded-lg border border-[var(--console-cyan)]/40 bg-[var(--console-cyan)]/10 px-2 py-1 text-[10px] text-[var(--console-cyan)] disabled:opacity-40"
          >
            {busy === 'preview' ? '預覽中…' : '預覽'}
          </button>
          <button
            type="button"
            disabled={busy !== 'idle'}
            onClick={() => void onApply()}
            className="rounded-lg border border-[var(--console-accent)]/40 bg-[var(--console-accent)]/10 px-2 py-1 text-[10px] text-[var(--console-accent)] disabled:opacity-40"
          >
            {busy === 'apply' ? '落地中…' : '落地'}
          </button>
        </div>
      </div>
      {error && <p className={`mt-2 ${consoleLayout.errorBar}`}>{error}</p>}
      {!compact && rows.length > 0 && (
        <ul className="mt-2 space-y-1 text-[10px] text-[var(--console-sub)]">
          {rows.slice(0, 5).map((row) => (
            <li key={row.id}>
              {(row as { title?: string; name?: string }).title ??
                (row as { name?: string }).name ??
                row.id}{' '}
              <span className="text-[var(--console-faint)]">· {row.world_status ?? 'pending_world'}</span>
            </li>
          ))}
          {rows.length > 5 && <li className="text-[var(--console-faint)]">…另有 {rows.length - 5} 筆</li>}
        </ul>
      )}
    </section>
  );
}
