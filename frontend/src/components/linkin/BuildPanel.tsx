/**
 * BuildPanel — 建築生成（風格、坐標、5000 方塊上限）與方案列表。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { deleteBuilding, fetchBuildings, fetchConstitution, generateBuilding, type Building } from '../../api/linkin';

const FALLBACK_REGION_STYLES: Record<string, string[]> = {
  织庭都: ['织梦典章', '白石圣殿', '契约广场', '金线回廊'],
  精灵森林: ['精灵古典', '林冠木石', '月光庭园', '树桥聚落'],
  裂隙港: ['蒸汽帆索', '自由贸易港', '裂隙工坊', '黄铜市集'],
  宁渊谷: ['水雾苔石', '隐士木屋', '灵脉神殿', '雾中庭园'],
};

export default function BuildPanel() {
  const [regionStyles, setRegionStyles] = useState<Record<string, string[]>>(FALLBACK_REGION_STYLES);
  const [prompt, setPrompt] = useState('在林冠间搭建一座月光庭园小桥');
  const [region, setRegion] = useState('精灵森林');
  const [style, setStyle] = useState('精灵古典');
  const [location, setLocation] = useState('120, 64, -300');
  const [blockCount, setBlockCount] = useState(800);
  const [result, setResult] = useState<Building | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const styles = useMemo(() => regionStyles[region] ?? Object.values(regionStyles).flat(), [region, regionStyles]);
  const overLimit = blockCount > 5000;

  const load = useCallback(async () => {
    try {
      const [data, constitution] = await Promise.all([fetchBuildings(), fetchConstitution().catch(() => null)]);
      setBuildings(data.buildings);
      if (constitution?.regions?.length) {
        const mapped: Record<string, string[]> = {};
        for (const row of constitution.regions) {
          const name = String(row['name'] || '').trim();
          const allowedRaw = row['allowed_styles'];
          const allowed = Array.isArray(allowedRaw)
            ? allowedRaw.map((s) => String(s))
            : [];
          if (name && allowed.length) mapped[name] = allowed;
        }
        if (Object.keys(mapped).length) setRegionStyles(mapped);
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!styles.includes(style)) {
      setStyle(styles[0] ?? '');
    }
  }, [styles, style]);

  const onGenerate = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await generateBuilding({ prompt, style, location, region, block_count: blockCount });
      setResult(data.building);
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
      await deleteBuilding(id);
      if (result?.id === id) setResult(null);
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
          <h2 className="text-sm font-semibold">建築生成</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">BuilderAI.generate：單次 ≤ 5000 方塊，風格必須匹配區域文化</p>
        </div>
        <button type="button" onClick={() => void load()} className="rounded-xl border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]">
          重新整理
        </button>
      </div>
      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="grid gap-3 lg:grid-cols-2">
        <label className="text-[10px] text-[#8a8f98]">描述 prompt
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-1 min-h-[96px] w-full rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[12px]" />
        </label>
        <div className="grid gap-2">
          <label className="text-[10px] text-[#8a8f98]">區域
            <select value={region} onChange={(e) => setRegion(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]">
              {Object.keys(regionStyles).map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <label className="text-[10px] text-[#8a8f98]">風格模板（依區域篩選）
            <select value={style} onChange={(e) => setStyle(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]">
              {styles.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <label className="text-[10px] text-[#8a8f98]">坐標 location
            <input value={location} onChange={(e) => setLocation(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]" />
          </label>
          <label className="text-[10px] text-[#8a8f98]">
            方塊數（上限 5000）
            <input type="number" min={1} max={8000} value={blockCount} onChange={(e) => setBlockCount(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]" />
          </label>
          {overLimit && <p className="text-[11px] text-[#FF9F0A]">超過 5000 方塊上限，送出將被後端拒絕</p>}
        </div>
      </div>

      <button type="button" disabled={busy} onClick={() => void onGenerate()} className="mt-4 self-start rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40">
        {busy ? '生成中' : '生成建築方案'}
      </button>

      {result && (
        <pre className="mt-4 overflow-auto rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3 text-[11px] leading-relaxed text-[#AEAEB2]">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}

      <h3 className="mb-2 mt-6 text-[11px] font-semibold text-[#8a8f98]">已規劃方案（{buildings.length}）</h3>
      <div className="space-y-2">
        {buildings.length === 0 && <p className="py-8 text-center text-xs text-[#636366]">尚無建築方案</p>}
        {buildings.map((item) => (
          <article key={item.id} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-[13px] font-medium">{item.style}</h4>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{item.region || String(item.location)}</span>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{item.block_count} 方塊</span>
              {item.status && <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{item.status}</span>}
            </div>
            <p className="mt-1 text-[12px] leading-relaxed text-[#AEAEB2]">{item.prompt}</p>
            {item.note && <p className="mt-1 text-[11px] text-[#8a8f98]">{item.note}</p>}
            <button
              type="button"
              disabled={busy}
              onClick={() => void onDelete(item.id)}
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
