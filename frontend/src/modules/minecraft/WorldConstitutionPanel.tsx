/**
 * WorldConstitutionPanel — 世界觀憲法檢視／編輯。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchConstitution, fetchEvents, fetchOverview, saveConstitution, type Constitution, type Overview, type WorldEvent } from '../../api/linkin';
import { activityNavPath } from '../../lib/monitorTabs';
import { eventCardUri, factionBannerUri, schoolBannerUri } from '../../lib/visualCards';
import MediaGallery from '../../components/media/MediaGallery';
import { McHeader, McMetrics, McPage } from './McChrome';

export default function WorldConstitutionPanel() {
  const [data, setData] = useState<Constitution | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [events, setEvents] = useState<WorldEvent[]>([]);
  const [jsonText, setJsonText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [constitution, ov, ev] = await Promise.all([
        fetchConstitution(),
        fetchOverview(),
        fetchEvents().catch(() => ({ events: [] as WorldEvent[] })),
      ]);
      setData(constitution);
      setOverview(ov);
      setEvents(ev.events);
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

  const worldName = data?.world_name_zh_hant || data?.world_name || '靈境·Linkin';
  const metrics = overview
    ? [
        { label: 'NPC', value: overview.npc_count },
        { label: '任務', value: overview.quest_count },
        { label: '事件', value: overview.event_count ?? events.length },
        { label: '知識庫', value: overview.compliance.rag.chroma ? 'Chroma' : 'JSON' },
      ]
    : [];

  return (
    <McPage>
      <McHeader
        title="世界觀"
        lead={`${worldName}。憲法約束 NPC、任務與道具；連線與建築派發在橋接頁。`}
        aside={
          <>
            <button type="button" onClick={() => void load()} className="mc-btn">重新整理</button>
            <button type="button" onClick={() => void save()} disabled={saving} className="mc-btn is-primary">
              {saving ? '儲存中' : '儲存憲法'}
            </button>
          </>
        }
      />
      <div className="mc-workspace">
      {error && <p className="mc-error">{error}</p>}
      {message && <p className="mc-note">{message}</p>}
      <McMetrics items={metrics} />

      <div className="mb-4 rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-3 py-2 text-[11px] text-[#8a8f98]">
        世界觀約束 NPC／任務／道具。Minecraft 連線、建築派發與審計在
        <a href="#/modules/minecraft/bridge" className="ml-1 text-[var(--console-accent)] hover:underline">
          {activityNavPath('minecraft')}
        </a>
        。
      </div>

      <div className="mb-4 grid gap-3 lg:grid-cols-2">
        <section className="rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">三大陣營</h3>
          {factions.length > 0 && (
            <div className="mb-3">
              <MediaGallery
                layout="grid"
                items={factions.map((faction) => ({
                  src: factionBannerUri(
                    String(faction.name ?? ''),
                    String(faction.alignment ?? ''),
                    String(faction.creed ?? ''),
                  ),
                  caption: String(faction.name ?? ''),
                  alt: String(faction.name ?? ''),
                  tags: String(faction.alignment ?? ''),
                }))}
              />
            </div>
          )}
          <div className="space-y-2">
            {factions.map((faction) => (
              <div key={String(faction.id || faction.name)} className="rounded-lg border border-white/[0.06] px-2.5 py-2">
                <p className="text-[13px] font-medium">{String(faction.name)} <span className="text-[10px] text-[#8a8f98]">{String(faction.alignment || '')}</span></p>
                <p className="mt-1 text-[11px] text-[var(--console-sub)]">{String(faction.creed || '')}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">靈絲術</h3>
          <p className="text-[13px] font-medium">
            {[data?.magic?.name, data?.magic?.alias].filter(Boolean).join(' · ') || '尚未記載'}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--console-sub)]">{String(data?.magic?.principle || '')}</p>
          {schools.length > 0 && (
            <div className="mt-3">
              <MediaGallery
                layout="grid"
                items={schools.map((school) => ({
                  src: schoolBannerUri(String(school.name ?? ''), String(school.domain ?? '')),
                  caption: `${school.name} · ${school.domain}`,
                  alt: String(school.name ?? ''),
                  tags: String(school.domain ?? ''),
                }))}
              />
            </div>
          )}
          <ul className="mt-2 space-y-1 text-[11px] text-[#8a8f98]">
            {schools.map((school) => (
              <li key={String(school.id || school.name)}>{school.name} — {school.domain}</li>
            ))}
          </ul>
        </section>
      </div>

      {events.length > 0 && (
        <section className="mb-4 rounded-xl border border-white/[0.08] bg-[var(--console-card)] p-3">
          <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">歷史事件</h3>
          <div className="mb-3">
            <MediaGallery
              layout="filmstrip"
              items={events.map((event) => ({
                src: eventCardUri(event.title || event.kind || event.id, event.kind),
                caption: event.title || event.kind || event.id,
                alt: event.title || event.id,
                tags: event.kind,
              }))}
            />
          </div>
          <ul className="space-y-2">
            {events.map((event) => (
              <li key={event.id} className="rounded-lg border border-white/[0.06] px-2.5 py-2">
                <p className="text-[13px] font-medium">{event.title || event.kind || event.id}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-[var(--console-sub)]">{event.text}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <details className="mc-panel">
        <summary className="mc-panel__title">直接編輯憲法</summary>
      <textarea
        value={jsonText}
        onChange={(e) => setJsonText(e.target.value)}
        className="mt-3 min-h-[280px] w-full rounded-xl border p-3 font-mono text-[12px] leading-relaxed"
      />
      </details>
      </div>
    </McPage>
  );
}
