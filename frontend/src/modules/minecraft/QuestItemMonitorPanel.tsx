/**
 * 任務／道具監控 — 庫存與落地狀態。
 */
import { useCallback, useState } from 'react';
import { fetchItems, fetchPendingWorldIntents, fetchQuestProgressSummary, fetchQuests } from '../../api/linkin';
import QuestRuntimeStrip from './QuestRuntimeStrip';
import { McHeader, McMetrics, McPage, McPanel } from './McChrome';
import { statusLabel, useVisibilityPoll } from './monitor/shared';

export default function QuestItemMonitorPanel() {
  const [quests, setQuests] = useState<Array<{ id: string; title: string; world_status?: string }>>([]);
  const [items, setItems] = useState<Array<{ id: string; name: string; world_status?: string }>>([]);
  const [pendingQ, setPendingQ] = useState(0);
  const [pendingI, setPendingI] = useState(0);
  const [activeProgress, setActiveProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [q, i, intents, progress] = await Promise.all([
        fetchQuests(),
        fetchItems(),
        fetchPendingWorldIntents(),
        fetchQuestProgressSummary(12),
      ]);
      setQuests((q.quests as Array<{ id: string; title: string; world_status?: string }>) ?? []);
      setItems((i.items as Array<{ id: string; name: string; world_status?: string }>) ?? []);
      setPendingQ(intents.pending?.quests?.length ?? 0);
      setPendingI(intents.pending?.items?.length ?? 0);
      setActiveProgress(progress?.active ?? 0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, 15000);

  const metrics = [
    { label: '任務', value: quests.length },
    { label: '道具', value: items.length },
    { label: '待落地任務', value: pendingQ },
    { label: '待落地道具', value: pendingI },
  ];
  if (activeProgress > 0) metrics.push({ label: '進行中', value: activeProgress });

  return (
    <McPage>
      <McHeader title="任務與道具" lead="庫存裡的任務、道具，以及玩家正在進行的進度。" />
      {error ? <p className="mc-error">{error}</p> : null}
      {loading && !quests.length && !items.length ? <p className="mc-empty">正在讀取任務與道具…</p> : null}
      {!error ? <McMetrics items={metrics} /> : null}
      <McPanel title="進行中的任務">
        <QuestRuntimeStrip />
      </McPanel>
      <McPanel title="任務">
        {!error && !loading && !quests.length ? (
          <p className="mc-empty">還沒有任務。</p>
        ) : (
          <ul className="mc-list">
            {quests.slice(0, 12).map((quest) => (
              <li key={quest.id} className="mc-row">
                <div className="mc-row__top">
                  <span className="mc-row__title">{quest.title}</span>
                  {quest.world_status ? (
                    <span className="mc-row__status">{statusLabel(quest.world_status)}</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </McPanel>
      <McPanel title="道具">
        {!error && !loading && !items.length ? (
          <p className="mc-empty">還沒有道具。</p>
        ) : (
          <ul className="mc-list">
            {items.slice(0, 12).map((item) => (
              <li key={item.id} className="mc-row">
                <div className="mc-row__top">
                  <span className="mc-row__title">{item.name}</span>
                  {item.world_status ? (
                    <span className="mc-row__status">{statusLabel(item.world_status)}</span>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </McPanel>
    </McPage>
  );
}
