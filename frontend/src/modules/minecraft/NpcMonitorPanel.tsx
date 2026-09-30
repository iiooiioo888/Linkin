/**
 * NPC 監控 — 庫存與落地狀態。
 */
import { useCallback, useState } from 'react';
import { fetchNpcs, fetchPendingWorldIntents, type NpcCard } from '../../api/linkin';
import { McHeader, McMetrics, McPage, McPanel } from './McChrome';
import { statusLabel, useVisibilityPoll } from './monitor/shared';

type NpcRow = NpcCard & { id?: string; world_status?: string; source?: string };

export default function NpcMonitorPanel() {
  const [npcs, setNpcs] = useState<NpcRow[]>([]);
  const [pending, setPending] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [npcRes, intentRes] = await Promise.all([fetchNpcs(), fetchPendingWorldIntents()]);
      setNpcs((npcRes.npcs as NpcRow[]) ?? []);
      setPending(intentRes.pending?.npcs?.length ?? 0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, 15000);

  const applied = npcs.filter((npc) => npc.world_status === 'applied').length;
  const partial = npcs.filter((npc) => npc.world_status === 'partial').length;

  return (
    <McPage>
      <McHeader title="NPC" lead="角色卡與是否已落到世界。沒有狀態的角色只顯示名字與陣營。" />
      {error ? <p className="mc-error">{error}</p> : null}
      {loading && !npcs.length ? <p className="mc-empty">正在讀取 NPC…</p> : null}
      {!error ? (
      <McMetrics
        items={[
          { label: '角色', value: npcs.length },
          { label: '待落地', value: pending },
          { label: '已落地', value: applied },
          { label: '部分落地', value: partial },
        ]}
      />
      ) : null}
      <McPanel title="角色清單">
        {!error && !loading && !npcs.length ? (
          <p className="mc-empty">還沒有 NPC。</p>
        ) : (
          <ul className="mc-list">
            {npcs.map((npc) => {
              const place = [npc.faction, npc.location].filter(Boolean).join(' · ');
              return (
                <li key={npc.id ?? npc.name} className="mc-row">
                  <div className="mc-row__top">
                    <span className="mc-row__title">{npc.name}</span>
                    {npc.world_status ? (
                      <span className="mc-row__status">{statusLabel(npc.world_status)}</span>
                    ) : null}
                  </div>
                  {place ? <p className="mc-row__meta">{place}</p> : null}
                  {npc.source === 'narrative_workspace' ? (
                    <p className="mc-row__meta">來自敘事工作區</p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </McPanel>
    </McPage>
  );
}
