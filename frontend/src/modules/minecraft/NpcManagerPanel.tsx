/**
 * NpcManagerPanel — 角色卡 CRUD 與對話測試。
 */
import { useCallback, useEffect, useState } from 'react';
import { createNpc, deleteNpc, fetchNpcs, npcDialogue, updateNpc, type NpcCard } from '../../api/linkin';
import { npcPortraitUri } from '../../lib/visualCards';
import MediaGallery, { VisualThumb } from '../../components/media/MediaGallery';
import PendingWorldIntentsBanner from './PendingWorldIntentsBanner';

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
      setRagNote(backend.chroma ? 'Chroma 檢索' : `RAG 降級：${backend.fallback ?? 'json'}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden apple-canvas text-[#f7f8f8]">
      <div className="flex items-center justify-between border-b border-white/[0.06] p-3">
        <h2 className="text-sm font-semibold">NPC 角色卡 <span className="text-xs text-[#8a8f98]">（{npcs.length}）</span></h2>
        <button type="button" onClick={() => void load()} className="rounded-md border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]">重新整理</button>
      </div>
      {error && <p className="border-b border-red-800 bg-red-900/30 px-3 py-2 text-xs text-red-300">{error}</p>}
      <div className="px-3 pt-3">
        <PendingWorldIntentsBanner kind="npc" compact />
      </div>
      <div className="grid min-h-0 flex-1 gap-0 overflow-hidden lg:grid-cols-[1fr_1.1fr]">
        <div className="overflow-y-auto border-b border-white/[0.06] p-3 lg:border-b-0 lg:border-r">
          {npcs.length === 0 && <p className="py-8 text-center text-xs text-[#636366]">尚無 NPC，請先建立角色卡</p>}
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
                className={`w-full rounded-lg border px-3 py-2 text-left ${selected === npc.id ? 'border-[#64D2FF]/40 bg-[#64D2FF]/10' : 'border-white/[0.08] bg-[#1C1C1E]'}`}
              >
                <div className="flex items-center gap-3">
                  <VisualThumb src={npcPortraitUri(npc.name, npc.faction, npc.occupation)} alt={npc.name} className="h-12 w-9" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[13px] font-medium">{npc.name}</p>
                      <span className="text-[10px] text-[#8a8f98]">{npc.faction}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] text-[#AEAEB2]">{npc.backstory}</p>
                  </div>
                </div>
                {npc.id && (
                  <span
                    className="mt-2 inline-block text-[10px] text-red-400"
                    onClick={(e) => {
                      e.stopPropagation();
                      void onDelete(npc.id as string);
                    }}
                  >
                    刪除
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
        <div className="overflow-y-auto p-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-[11px] font-semibold text-[#8a8f98]">{selected ? '編輯角色卡' : '新增角色卡'}</h3>
            {selected && (
              <button type="button" onClick={onNew} className="text-[10px] text-[#8a8f98] hover:text-[#f7f8f8]">
                改為新增
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2">
            {([
              ['name', '名稱'],
              ['faction', '陣營'],
              ['occupation', '職業'],
              ['location', '地點'],
              ['personality', '性格'],
              ['speech_style', '語言風格'],
            ] as Array<[keyof NpcCard, string]>).map(([key, label]) => (
              <label key={key} className="text-[10px] text-[#8a8f98]">
                {label}
                <input value={String(form[key] ?? '')} onChange={(e) => setField(key, e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[#f7f8f8]" />
              </label>
            ))}
          </div>
          <label className="mt-2 block text-[10px] text-[#8a8f98]">
            背景故事（必填）
            <textarea value={form.backstory} onChange={(e) => setField('backstory', e.target.value)} className="mt-1 min-h-[72px] w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
          </label>
          <button type="button" disabled={busy} onClick={() => void onSave()} className="mt-2 rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40">
            {selected ? '更新 NPC' : '建立 NPC'}
          </button>

          <h3 className="mb-2 mt-5 text-[11px] font-semibold text-[#8a8f98]">對話測試</h3>
          <p className="mb-1 text-[10px] text-[#636366]">{selected ? `對象：${npcs.find((n) => n.id === selected)?.name}` : '請先在左側選取 NPC'}</p>
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} placeholder="玩家對白" className="min-h-[64px] w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
          <button type="button" disabled={busy || !selected} onClick={() => void onTalk()} className="mt-2 rounded-lg border border-white/[0.08] px-3 py-1.5 text-[12px] disabled:opacity-40">
            送出對話
          </button>
          {ragNote && <p className="mt-2 text-[10px] text-[#64D2FF]">{ragNote}</p>}
          {reply && <p className="mt-2 whitespace-pre-wrap rounded-lg border border-white/[0.06] bg-[#1C1C1E] px-3 py-2 text-[12px] leading-relaxed">{reply}</p>}
        </div>
      </div>
    </div>
  );
}
