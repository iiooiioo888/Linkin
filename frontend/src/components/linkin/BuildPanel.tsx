/**
 * BuildPanel — 建築生成、Sponge Schematic v3 與 Three.js 預覽。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  deleteBuilding,
  dispatchBuilding,
  fetchBuildingPreview,
  fetchBuildings,
  fetchConstitution,
  generateBuilding,
  importSchematic,
  importSchematicBase64,
  schematicUrl,
  type Building,
  type BuildingPreview,
} from '../../api/linkin';
import BuildingViewer from './BuildingViewer';

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
  const [preview, setPreview] = useState<BuildingPreview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<'idle' | 'generate' | 'dispatch' | 'delete' | 'preview' | 'import'>('idle');
  const [dispatchNote, setDispatchNote] = useState<string | null>(null);
  const [b64Input, setB64Input] = useState('');
  const [b64Copied, setB64Copied] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

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
          const allowed = Array.isArray(allowedRaw) ? allowedRaw.map((s) => String(s)) : [];
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

  const loadPreview = async (id: string, fallback?: BuildingPreview | null) => {
    if (fallback && fallback.voxels?.length) {
      setPreview(fallback);
      setSelectedId(id);
      return;
    }
    setBusy('preview');
    try {
      const data = await fetchBuildingPreview(id);
      setPreview(data);
      setSelectedId(id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy((current) => (current === 'preview' ? 'idle' : current));
    }
  };

  const onGenerate = async () => {
    setBusy('generate');
    setError(null);
    try {
      const data = await generateBuilding({ prompt, style, location, region, block_count: blockCount });
      setResult(data.building);
      await loadPreview(data.building.id, data.preview);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const onDispatch = async (id: string) => {
    setBusy('dispatch');
    setError(null);
    setDispatchNote(null);
    try {
      const data = await dispatchBuilding(id);
      const mcp = data.minecraft;
      setDispatchNote(
        mcp && mcp.dry_run
          ? '已乾跑派發標記方塊（未連 Minecraft）。設定 EVOL_MC_MCP_ENABLED 後會寫入世界。'
          : '已派發標記方塊到 Minecraft 錨點。',
      );
      setResult(data.building);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const onDelete = async (id: string) => {
    setBusy('delete');
    setError(null);
    try {
      await deleteBuilding(id);
      if (result?.id === id) setResult(null);
      if (selectedId === id) {
        setSelectedId(null);
        setPreview(null);
      }
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const onImport = async (file: File | undefined) => {
    if (!file) return;
    setBusy('import');
    setError(null);
    try {
      const data = await importSchematic(file, { prompt, style, location, region });
      setResult(data.building);
      await loadPreview(data.building.id, data.preview);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const onCopyBase64 = async () => {
    const text = preview?.schematic_base64;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setB64Copied(true);
      window.setTimeout(() => setB64Copied(false), 1600);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onImportBase64 = async () => {
    const text = b64Input.trim();
    if (!text) {
      setError('請貼上 .schem 的 Base64');
      return;
    }
    setBusy('import');
    setError(null);
    try {
      const data = await importSchematicBase64(text, { prompt, style, location, region });
      setResult(data.building);
      setB64Input('');
      await loadPreview(data.building.id, data.preview);
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">建築生成</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">BuilderAI.generate → nbtlib Gzip .schem（Sponge v3）＋ Base64，Three.js 預覽，單次 ≤ 5000 方塊</p>
        </div>
        <button type="button" onClick={() => void load()} className="rounded-xl border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]">
          重新整理
        </button>
      </div>
      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}
      {dispatchNote && <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{dispatchNote}</div>}

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="flex min-h-[320px] flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-[#111113]">
          <BuildingViewer preview={preview} loading={busy === 'preview' || busy === 'generate' || busy === 'import'} />
        </div>
        <div className="grid gap-2">
          <label className="text-[10px] text-[#8a8f98]">描述 prompt
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-1 min-h-[72px] w-full rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[12px]" />
          </label>
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
          <div className="mt-1 flex flex-wrap gap-2">
            <button type="button" disabled={busy !== 'idle'} onClick={() => void onGenerate()} className="rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40">
              {busy === 'generate' ? '生成中' : '生成建築方案'}
            </button>
            <button
              type="button"
              disabled={busy !== 'idle'}
              onClick={() => fileRef.current?.click()}
              className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[#AEAEB2] disabled:opacity-40"
            >
              {busy === 'import' ? '匯入中' : '匯入 .schem'}
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".schem,.nbt"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                void onImport(file);
              }}
            />
            {selectedId && (
              <a
                href={schematicUrl(selectedId)}
                download={`${selectedId}.schem`}
                className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[#AEAEB2]"
              >
                下載 .schem
              </a>
            )}
          </div>
          <label className="text-[10px] text-[#8a8f98]">
            Base64 .schem（可貼上或從目前預覽複製）
            <textarea
              value={b64Input}
              onChange={(e) => setB64Input(e.target.value)}
              placeholder="H4sIAAAAAAAAA..."
              className="mt-1 min-h-[72px] w-full rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 font-mono text-[11px] text-[#AEAEB2]"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy !== 'idle' || !preview?.schematic_base64}
              onClick={() => void onCopyBase64()}
              className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[#AEAEB2] disabled:opacity-40"
            >
              {b64Copied ? '已複製' : '複製目前 Base64'}
            </button>
            <button
              type="button"
              disabled={busy !== 'idle' || !b64Input.trim()}
              onClick={() => void onImportBase64()}
              className="rounded-lg border border-white/[0.12] px-3 py-1.5 text-[12px] text-[#AEAEB2] disabled:opacity-40"
            >
              從 Base64 匯入
            </button>
          </div>
        </div>
      </div>

      {result && (
        <p className="mt-3 text-[11px] text-[#8a8f98]">
          {result.style} · {result.width ?? '?'}×{result.height ?? '?'}×{result.length ?? '?'} · v{result.schematic_version ?? 3}
          {result.note ? ` · ${result.note}` : ''}
        </p>
      )}

      <h3 className="mb-2 mt-6 text-[11px] font-semibold text-[#8a8f98]">已規劃方案（{buildings.length}）</h3>
      <div className="space-y-2">
        {buildings.length === 0 && <p className="py-8 text-center text-xs text-[#636366]">尚無建築方案</p>}
        {buildings.map((item) => (
          <article
            key={item.id}
            className={`rounded-xl border p-3 ${selectedId === item.id ? 'border-[#64D2FF]/40 bg-[#64D2FF]/5' : 'border-white/[0.08] bg-[#1C1C1E]'}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-[13px] font-medium">{item.style}</h4>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{item.region || String(item.location)}</span>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{item.voxel_count || item.block_count} 方塊</span>
              {item.width && item.height && item.length && (
                <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">
                  {item.width}×{item.height}×{item.length}
                </span>
              )}
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">v{item.schematic_version ?? 3}</span>
              {item.status && <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{item.status}</span>}
            </div>
            <p className="mt-1 text-[12px] leading-relaxed text-[#AEAEB2]">{item.prompt}</p>
            {item.note && <p className="mt-1 text-[11px] text-[#8a8f98]">{item.note}</p>}
            <div className="mt-2 flex flex-wrap gap-3">
              <button type="button" disabled={busy !== 'idle'} onClick={() => void loadPreview(item.id)} className="text-[10px] text-[#64D2FF] disabled:opacity-40">
                3D 預覽
              </button>
              <button type="button" disabled={busy !== 'idle'} onClick={() => void onDispatch(item.id)} className="text-[10px] text-[#64D2FF] disabled:opacity-40">
                發送到 Minecraft
              </button>
              <a href={schematicUrl(item.id)} download={`${item.id}.schem`} className="text-[10px] text-[#AEAEB2]">
                下載 .schem
              </a>
              <button type="button" disabled={busy !== 'idle'} onClick={() => void onDelete(item.id)} className="text-[10px] text-red-400 disabled:opacity-40">
                刪除
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
