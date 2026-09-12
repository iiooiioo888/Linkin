/**
 * NPC 監控 — 庫存、pending_world / applied / partial。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchNpcs, fetchPendingWorldIntents, type NpcCard } from '../../api/linkin';
import { KpiSparkCard, StackBar } from '../../components/ui/monitor';
import {
  ConsoleCard,
  ConsoleCardHeader,
  ConsoleCenterColumn,
  ConsoleColumnScroll,
  KpiGrid6,
  PanelAlert,
  PanelShell,
} from '../../components/ui/ConsoleLayout';
import { statusLabel, statusStripe } from './monitor/shared';

type NpcRow = NpcCard & { id?: string; world_status?: string; source?: string };

export default function NpcMonitorPanel() {
  const [npcs, setNpcs] = useState<NpcRow[]>([]);
  const [pending, setPending] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [npcRes, intentRes] = await Promise.all([fetchNpcs(), fetchPendingWorldIntents()]);
      setNpcs(npcRes.npcs as NpcRow[]);
      setPending(intentRes.pending.npcs.length);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = { pending_world: 0, applied: 0, partial: 0, other: 0 };
  for (const npc of npcs) {
    const st = npc.world_status ?? 'other';
    if (st in counts) counts[st as keyof typeof counts] += 1;
    else counts.other += 1;
  }

  const stack = [
    { label: '待落地', value: counts.pending_world || pending, color: 'var(--console-amber)' },
    { label: '已落地', value: counts.applied, color: 'var(--console-green)' },
    { label: '部分', value: counts.partial, color: 'var(--console-blue)' },
  ];

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          <KpiGrid6>
            <KpiSparkCard label="NPC 總數" value={String(npcs.length)} accent />
            <KpiSparkCard label="待落地" value={String(pending)} />
            <KpiSparkCard label="已落地" value={String(counts.applied)} />
            <KpiSparkCard label="部分" value={String(counts.partial)} />
          </KpiGrid6>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>狀態分佈</ConsoleCardHeader>
            <div className="px-3 pb-3"><StackBar segments={stack} /></div>
          </ConsoleCard>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>NPC 清單 · world_status</ConsoleCardHeader>
            <ul className="divide-y divide-[var(--console-border)]">
              {npcs.map((npc) => (
                <li key={npc.id ?? npc.name} className="mon-task-card px-3 py-2 text-xs" data-priority={statusStripe(npc.world_status ?? 'other')}>
                  <div className="flex justify-between gap-2">
                    <span className="font-medium">{npc.name}</span>
                    <span className="text-[var(--console-accent)]">{statusLabel(npc.world_status ?? '—')}</span>
                  </div>
                  <div className="text-[var(--console-faint)]">{npc.faction} · {npc.location}</div>
                  {npc.source === 'narrative_workspace' ? (
                    <div className="mt-1 text-[10px] text-[var(--console-cyan)]">敘事工作區 · 可從世界意圖落地</div>
                  ) : null}
                </li>
              ))}
            </ul>
          </ConsoleCard>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
