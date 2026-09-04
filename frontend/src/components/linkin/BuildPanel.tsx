/**
 * BuildPanel — 建築生成（風格、坐標、5000 方塊上限）。
 */
import { useState } from 'react';
import { generateBuilding, type Building } from '../../api/linkin';

const STYLES = ['织梦典章', '白石圣殿', '精灵古典', '林冠木石', '月光庭园', '蒸汽帆索', '自由贸易港', '水雾苔石', '隐士木屋'];

export default function BuildPanel() {
  const [prompt, setPrompt] = useState('在林冠间搭建一座月光庭园小桥');
  const [style, setStyle] = useState('精灵古典');
  const [region, setRegion] = useState('精灵森林');
  const [location, setLocation] = useState('120, 64, -300');
  const [blockCount, setBlockCount] = useState(800);
  const [result, setResult] = useState<Building | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const overLimit = blockCount > 5000;

  const onGenerate = async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await generateBuilding({ prompt, style, location, region, block_count: blockCount });
      setResult(data.building);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4">
        <h2 className="text-sm font-semibold">建築生成</h2>
        <p className="mt-0.5 text-[11px] text-[#8a8f98]">BuilderAI.generate：單次 ≤ 5000 方塊，風格必須匹配區域文化</p>
      </div>
      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="grid gap-3 lg:grid-cols-2">
        <label className="text-[10px] text-[#8a8f98]">描述 prompt
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-1 min-h-[96px] w-full rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-[12px]" />
        </label>
        <div className="grid gap-2">
          <label className="text-[10px] text-[#8a8f98]">區域
            <select value={region} onChange={(e) => setRegion(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]">
              <option value="织庭都">織庭都</option>
              <option value="精灵森林">精靈森林</option>
              <option value="裂隙港">裂隙港</option>
              <option value="宁渊谷">寧淵谷</option>
            </select>
          </label>
          <label className="text-[10px] text-[#8a8f98]">風格模板
            <select value={style} onChange={(e) => setStyle(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]">
              {STYLES.map((item) => (
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
    </div>
  );
}
