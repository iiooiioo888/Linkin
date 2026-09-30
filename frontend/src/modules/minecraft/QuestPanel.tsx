/**
 * QuestPanel — 任務生成（類型／難度）與列表。
 */
import { useCallback, useEffect, useState } from 'react';
import { deleteQuest, fetchQuests, generateQuest, type Quest } from '../../api/linkin';
import { mcLabel, NARRATIVE_REGION_OPTIONS } from './localeRegions';
import { questCardUri } from '../../lib/visualCards';
import MediaGallery from '../../components/media/MediaGallery';
import PendingWorldIntentsBanner from './PendingWorldIntentsBanner';
import { McHeader, McPage, McPanel } from './McChrome';

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
    <McPage>
      <McHeader
        title="任務"
        lead="生成前會先對照世界觀。類型只有主線、支線、日常。"
        aside={<button type="button" onClick={() => void load()} className="mc-btn">重新整理</button>}
      />
      <div className="mc-workspace">
      <PendingWorldIntentsBanner kind="quest" compact />
      {error && <p className="mc-error">{error}</p>}

      <McPanel title="生成任務" hint="主線、支線、日常">
        <div className="mc-form">
          <label>玩家
            <input value={playerId} onChange={(e) => setPlayerId(e.target.value)} />
          </label>
          <label>類型
            <select value={questType} onChange={(e) => setQuestType(e.target.value)}>
              <option value="主线">主線</option>
              <option value="支线">支線</option>
              <option value="日常">日常</option>
            </select>
          </label>
          <label>難度
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="简单">簡單</option>
              <option value="普通">普通</option>
              <option value="困难">困難</option>
            </select>
          </label>
          <label>區域
            <select value={region} onChange={(e) => setRegion(e.target.value)}>
              {NARRATIVE_REGION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <div>
            <button type="button" disabled={busy} onClick={() => void onGenerate()} className="mc-btn is-primary">
              {busy ? '生成中' : '生成任務'}
            </button>
          </div>
        </div>
      </McPanel>

      <McPanel title="任務列表" hint={quests.length ? `${quests.length} 筆` : undefined}>
        {quests.length === 0 ? <p className="mc-empty">還沒有任務。選好類型與區域後即可生成。</p> : null}
        {quests.length > 0 ? (
          <MediaGallery
            layout="filmstrip"
            items={quests.map((quest) => ({
              src: questCardUri(quest.title, quest.quest_type, quest.difficulty),
              caption: `${quest.title} · ${mcLabel(quest.quest_type)}`,
              alt: quest.title,
              tags: `${quest.quest_type},${quest.difficulty}`,
            }))}
          />
        ) : null}
        <ul className="mc-list" style={{ marginTop: quests.length ? 12 : 0 }}>
          {quests.map((quest) => (
            <li key={quest.id} className="mc-row">
              <div className="mc-row__top">
                <span className="mc-row__title">{quest.title}</span>
                <span className="mc-row__meta">{mcLabel(quest.quest_type)} · {mcLabel(quest.difficulty)}</span>
              </div>
              {quest.description ? <p className="mc-note">{quest.description}</p> : null}
              <button type="button" disabled={busy} onClick={() => void onDelete(quest.id)} className="mc-danger">
                刪除
              </button>
            </li>
          ))}
        </ul>
      </McPanel>
      </div>
    </McPage>
  );
}
