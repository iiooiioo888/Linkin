/**
 * WorldConstitutionPanel — 世界觀憲法檢視／編輯。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchConstitution, fetchOverview, saveConstitution, type Constitution, type Overview } from '../../api/linkin';

export default function WorldConstitutionPanel() {
  const [data, setData] = useState<Constitution | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [jsonText, setJsonText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [constitution, ov] = await Promise.all([fetchConstitution(), fetchOverview()]);
      setData(constitution);
      setOverview(ov);
      setJsonText(JSON.stringify(constitution, null, 2));
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const parsed = JSON.parse(jsonText) as Record<string, unknown>;
      const saved = await saveConstitution({ ...parsed, replace: true });
      setData(saved);
      setJsonText(JSON.stringify(saved, null, 2));
      setMessage('憲法已更新');
      setOverview(await fetchOverview());
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const factions = data?.factions ?? [];
  const schools = (data?.magic?.schools as Array<Record<string, string>> | undefined) ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">世界觀憲法</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            {data?.world_name_zh_hant || data?.world_name || '靈境·Linkin'} · 最高約束層
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void load()} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]">
            重新整理
          </button>
          <button type="button" onClick={() => void save()} disabled={saving} className="rounded-xl border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-2 py-1 text-[11px] text-[#64D2FF] disabled:opacity-40">
            {saving ? '儲存中' : '儲存憲法'}
          </button>
        </div>
      </div>

      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}
      {message && <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{message}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[
          { label: 'NPC', value: String(overview?.npc_count ?? '—') },
          { label: '任務', value: String(overview?.quest_count ?? '—') },
          { label: '事件', value: String(overview?.event_count ?? '—') },
          { label: 'RAG', value: overview?.compliance.rag.chroma ? 'Chroma' : 'JSON 降級' },
        ].map((card) => (
          <div key={card.label} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2">
            <p className="text-[10px] text-[#8a8f98]">{card.label}</p>
            <p className="text-sm font-medium">{card.value}</p>
          </div>
        ))}
      </div>

      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">三大陣營</h3>
          <div className="space-y-2">
            {factions.map((faction) => (
              <div key={String(faction.id || faction.name)} className="rounded-lg border border-white/[0.06] px-2.5 py-2">
                <p className="text-[13px] font-medium">{String(faction.name)} <span className="text-[10px] text-[#8a8f98]">{String(faction.alignment || '')}</span></p>
                <p className="mt-1 text-[11px] text-[#AEAEB2]">{String(faction.creed || '')}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">靈絲術</h3>
          <p className="text-[13px] font-medium">{String(data?.magic?.name || '—')} · {String(data?.magic?.alias || '')}</p>
          <p className="mt-1 text-[11px] leading-relaxed text-[#AEAEB2]">{String(data?.magic?.principle || '')}</p>
          <ul className="mt-2 space-y-1 text-[11px] text-[#8a8f98]">
            {schools.map((school) => (
              <li key={String(school.id || school.name)}>{school.name} — {school.domain}</li>
            ))}
          </ul>
        </section>
      </div>

      <label className="mb-1 text-[11px] text-[#8a8f98]">憲法 JSON</label>
      <textarea
        value={jsonText}
        onChange={(e) => setJsonText(e.target.value)}
        className="min-h-[280px] flex-1 rounded-xl border border-white/[0.08] bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-[#d4d4d8] outline-none focus:border-[#64D2FF]/40"
      />
    </div>
  );
}
