/**
 * 任務／道具監控 — 世界意圖狀態帶。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchItems, fetchPendingWorldIntents, fetchQuests } from '../../api/linkin';
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

export default function QuestItemMonitorPanel() {
  const [quests, setQuests] = useState<Array<{ id: string; title: string; world_status?: string }>>([]);
  const [items, setItems] = useState<Array<{ id: string; name: string; world_status?: string }>>([]);
  const [pendingQ, setPendingQ] = useState(0);
  const [pendingI, setPendingI] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [q, i, intents] = await Promise.all([fetchQuests(), fetchItems(), fetchPendingWorldIntents()]);
      setQuests(q.quests as Array<{ id: string; title: string; world_status?: string }>);
      setItems(i.items as Array<{ id: string; name: string; world_status?: string }>);
      setPendingQ(intents.pending.quests.length);
      setPendingI(intents.pending.items.length);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const questStack = [
    { label: '待落地', value: pendingQ, color: 'var(--console-amber)' },
    { label: '已落地', value: quests.filter((q) => q.world_status === 'applied').length, color: 'var(--console-green)' },
    { label: '部分', value: quests.filter((q) => q.world_status === 'partial').length, color: 'var(--console-blue)' },
  ];
  const itemStack = [
    { label: '待落地', value: pendingI, color: 'var(--console-amber)' },
    { label: '已落地', value: items.filter((x) => x.world_status === 'applied').length, color: 'var(--console-green)' },
    { label: '部分', value: items.filter((x) => x.world_status === 'partial').length, color: 'var(--console-blue)' },
  ];

  return (
    <PanelShell>
      <ConsoleCenterColumn>
        <ConsoleColumnScroll>
          {error ? <PanelAlert tone="error">{error}</PanelAlert> : null}
          <KpiGrid6>
            <KpiSparkCard label="任務" value={String(quests.length)} accent />
            <KpiSparkCard label="道具" value={String(items.length)} />
            <KpiSparkCard label="待落地任務" value={String(pendingQ)} />
            <KpiSparkCard label="待落地道具" value={String(pendingI)} />
          </KpiGrid6>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>任務狀態</ConsoleCardHeader>
            <div className="px-3 pb-3"><StackBar segments={questStack} /></div>
            <ul className="divide-y divide-[var(--console-border)] border-t border-[var(--console-border)]">
              {quests.slice(0, 12).map((q) => (
                <li key={q.id} className="mon-task-card px-3 py-2 text-xs" data-priority={statusStripe(q.world_status ?? 'other')}>
                  <div className="flex justify-between"><span>{q.title}</span><span>{statusLabel(q.world_status ?? '—')}</span></div>
                </li>
              ))}
            </ul>
          </ConsoleCard>
          <ConsoleCard className="mt-3">
            <ConsoleCardHeader>道具狀態</ConsoleCardHeader>
            <div className="px-3 pb-3"><StackBar segments={itemStack} /></div>
            <ul className="divide-y divide-[var(--console-border)] border-t border-[var(--console-border)]">
              {items.slice(0, 12).map((item) => (
                <li key={item.id} className="mon-task-card px-3 py-2 text-xs" data-priority={statusStripe(item.world_status ?? 'other')}>
                  <div className="flex justify-between"><span>{item.name}</span><span>{statusLabel(item.world_status ?? '—')}</span></div>
                </li>
              ))}
            </ul>
          </ConsoleCard>
        </ConsoleColumnScroll>
      </ConsoleCenterColumn>
    </PanelShell>
  );
}
