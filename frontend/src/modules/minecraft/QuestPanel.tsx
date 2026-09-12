/**
 * QuestPanel — 任務生成（類型／難度）與列表。
 */
import { useCallback, useEffect, useState } from 'react';
import { deleteQuest, fetchQuests, generateQuest, type Quest } from '../../api/linkin';
import { questCardUri } from '../../lib/visualCards';
import MediaGallery from '../../components/media/MediaGallery';
import PendingWorldIntentsBanner from './PendingWorldIntentsBanner';

export default function QuestPanel() {
  const [quests, setQuests] = useState<Quest[]>([]);
  const [playerId, setPlayerId] = useState('traveler-01');
  const [questType, setQuestType] = useState('支线');
  const [difficulty, setDifficulty] = useState('普通');
  const [region, setRegion] = useState('织庭都');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchQuests();
      setQuests(data.quests);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onGenerate = async () => {
    setBusy(true);
    setError(null);
    try {
      await generateQuest({ playerId, questType, difficulty, region });
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await deleteQuest(id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">任務</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">生成前會檢索世界觀知識庫；類型限主線／支線／日常</p>
        </div>
        <button type="button" onClick={() => void load()} className="rounded-xl border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]">重新整理</button>
      </div>
      <PendingWorldIntentsBanner kind="quest" compact />
      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="mb-4 grid gap-2 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-[10px] text-[#8a8f98]">玩家 ID
          <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
        </label>
        <label className="text-[10px] text-[#8a8f98]">類型
          <select value={questType} onChange={(e) => setQuestType(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]">
            <option value="主线">主線</option>
            <option value="支线">支線</option>
            <option value="日常">日常</option>
          </select>
        </label>
        <label className="text-[10px] text-[#8a8f98]">難度
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]">
            <option value="简单">簡單</option>
            <option value="普通">普通</option>
            <option value="困难">困難</option>
          </select>
        </label>
        <label className="text-[10px] text-[#8a8f98]">區域
          <select value={region} onChange={(e) => setRegion(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]">
            <option value="织庭都">織庭都</option>
            <option value="精灵森林">精靈森林</option>
            <option value="裂隙港">裂隙港</option>
            <option value="宁渊谷">寧淵谷</option>
          </select>
        </label>
        <div className="flex items-end">
          <button type="button" disabled={busy} onClick={() => void onGenerate()} className="w-full rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40">
            {busy ? '生成中' : '生成任務'}
          </button>
        </div>
      </div>

      <div className="space-y-2">
        {quests.length === 0 && <p className="py-10 text-center text-xs text-[#636366]">尚無任務</p>}
        {quests.length > 0 && (
          <MediaGallery
            layout="filmstrip"
            items={quests.map((quest) => ({
              src: questCardUri(quest.title, quest.quest_type, quest.difficulty),
              caption: `${quest.title} · ${quest.quest_type}`,
              alt: quest.title,
              tags: `${quest.quest_type},${quest.difficulty}`,
            }))}
          />
        )}
        {quests.map((quest) => (
          <article key={quest.id} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-[13px] font-medium">{quest.title}</h3>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{quest.quest_type}</span>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{quest.difficulty}</span>
            </div>
            <p className="mt-1 text-[12px] leading-relaxed text-[#AEAEB2]">{quest.description}</p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void onDelete(quest.id)}
              className="mt-2 text-[10px] text-red-400 disabled:opacity-40"
            >
              刪除
            </button>
          </article>
        ))}
      </div>
    </div>
  );
}
