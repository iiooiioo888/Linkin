/**
 * NpcManagerPanel — 角色卡 CRUD 與對話測試。
 */
import { useCallback, useEffect, useState } from 'react';
import { createNpc, deleteNpc, fetchNpcs, npcDialogue, updateNpc, type NpcCard } from '../../api/linkin';
import { npcPortraitUri } from '../../lib/visualCards';
import MediaGallery, { VisualThumb } from '../../components/media/MediaGallery';
import PendingWorldIntentsBanner from './PendingWorldIntentsBanner';
import { McHeader, McPage } from './McChrome';

const EMPTY: NpcCard = {
  name: '',
  faction: '织庭盟',
  occupation: '',
  personality: '',
  backstory: '',
  location: '织庭都',
  speech_style: '',
};

export default function NpcManagerPanel() {
  const [npcs, setNpcs] = useState<NpcCard[]>([]);
  const [form, setForm] = useState<NpcCard>(EMPTY);
  const [selected, setSelected] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [reply, setReply] = useState<string | null>(null);
  const [ragNote, setRagNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchNpcs();
      setNpcs(data.npcs);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setField = (key: keyof NpcCard, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const selectNpc = (npc: NpcCard) => {
    setSelected(npc.id ?? null);
    setForm({
      name: npc.name,
      faction: npc.faction,
      occupation: npc.occupation,
      personality: npc.personality,
      backstory: npc.backstory,
      location: npc.location,
      speech_style: npc.speech_style,
      relationships: npc.relationships,
    });
  };

  const onSave = async () => {
    setBusy(true);
    setError(null);
    try {
      if (selected) {
        await updateNpc(selected, form);
      } else {
        await createNpc(form);
        setForm(EMPTY);
      }
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onNew = () => {
    setSelected(null);
    setForm(EMPTY);
    setReply(null);
    setRagNote(null);
  };

  const onDelete = async (id: string) => {
    setBusy(true);
    try {
      await deleteNpc(id);
      if (selected === id) {
        setSelected(null);
        setForm(EMPTY);
      }
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onTalk = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const data = await npcDialogue(selected, message);
      setReply(data.reply);
      const backend = (data.rag?.backend as { chroma?: boolean; fallback?: string } | undefined) ?? {};
      setRagNote(backend.chroma ? '已用世界記憶檢索' : '世界記憶暫時改走本地備援');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <McPage fill>
      <McHeader
        title="NPC"
        lead={npcs.length ? `目前 ${npcs.length} 張角色卡。選一張可改設定，或直接試對話。` : '還沒有角色卡。右側可新增，對話會對照世界觀。'}
        aside={<button type="button" onClick={() => void load()} className="mc-btn">重新整理</button>}
      />
      <div className="mc-workspace mc-workspace--fill">
      {error && <p className="mc-error">{error}</p>}
      <PendingWorldIntentsBanner kind="npc" compact />
      <div className="mc-split">
        <div className="mc-split__pane">
          {npcs.length === 0 && <p className="mc-empty">還沒有角色卡。右側可新增。</p>}
          {npcs.length > 0 && (
            <div className="mb-3">
              <MediaGallery
                layout="mosaic"
                items={npcs.map((npc) => ({
                  src: npcPortraitUri(npc.name, npc.faction, npc.occupation),
                  caption: `${npc.name} · ${npc.faction}`,
                  alt: npc.name,
                  tags: npc.faction,
                  size: npc.occupation ? 'large' : 'small',
                }))}
                filter
                onOpen={(_, index) => {
                  const npc = npcs[index];
                  if (npc) selectNpc(npc);
                }}
              />
            </div>
          )}
          <div className="space-y-2">
            {npcs.map((npc) => (
              <button
                key={npc.id}
                type="button"
                onClick={() => selectNpc(npc)}
                className={`mc-row${selected === npc.id ? ' is-on' : ''}`}
              >
                <div className="mc-row__top">
                  <span className="mc-row__title">{npc.name}</span>
                  <span className="mc-row__meta">{npc.faction}</span>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                  <VisualThumb src={npcPortraitUri(npc.name, npc.faction, npc.occupation)} alt={npc.name} className="h-12 w-9" />
                  <p className="mc-note" style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{npc.backstory}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
        <div className="mc-split__pane">
          <div className="mc-row__top">
            <h3>{selected ? '編輯角色卡' : '新增角色卡'}</h3>
          </div>
          <div className="mc-form">
            {([
              ['name', '名稱'],
              ['faction', '陣營'],
              ['occupation', '職業'],
              ['location', '地點'],
              ['personality', '性格'],
              ['speech_style', '語言風格'],
            ] as Array<[keyof NpcCard, string]>).map(([key, label]) => (
              <label key={key}>
                {label}
                <input value={String(form[key] ?? '')} onChange={(e) => setField(key, e.target.value)} />
              </label>
            ))}
          </div>
          <label>
            背景故事
            <textarea value={form.backstory} onChange={(e) => setField('backstory', e.target.value)} />
          </label>
          <div className="mc-actions">
            <button type="button" disabled={busy} onClick={() => void onSave()} className="mc-btn is-primary">
              {selected ? '儲存角色卡' : '建立角色卡'}
            </button>
            {selected ? (
              <button type="button" className="mc-btn" onClick={onNew}>改為新增</button>
            ) : null}
            {selected ? (
              <button type="button" className="mc-danger" disabled={busy} onClick={() => void onDelete(selected)}>
                刪除這張角色卡
              </button>
            ) : null}
          </div>

          <h3 style={{ marginTop: 20 }}>試對話</h3>
          <p className="mc-note">{selected ? `對象：${npcs.find((n) => n.id === selected)?.name}` : '先在左側選一張角色卡。'}</p>
          <label>
            玩家對白
            <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="想跟這個角色說的話" />
          </label>
          <div className="mc-actions">
            <button type="button" disabled={busy || !selected} onClick={() => void onTalk()} className="mc-btn">
              送出
            </button>
          </div>
          {ragNote ? <p className="mc-note">{ragNote}</p> : null}
          {reply ? <p className="mc-reply">{reply}</p> : null}
        </div>
      </div>
      </div>
    </McPage>
  );
}
