/**
 * ItemPanel — 道具庫表格與新增表單。
 */
import { useCallback, useEffect, useState } from 'react';
import { createItem, fetchItems, type Item } from '../../api/linkin';

export default function ItemPanel() {
  const [items, setItems] = useState<Item[]>([]);
  const [name, setName] = useState('');
  const [type, setType] = useState('武器');
  const [rarity, setRarity] = useState('common');
  const [power, setPower] = useState(8);
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchItems();
      setItems(data.items);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async () => {
    setBusy(true);
    setError(null);
    try {
      await createItem({
        name,
        type,
        rarity,
        attributes: { power },
        description,
      });
      setName('');
      setDescription('');
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
          <h2 className="text-sm font-semibold">道具庫</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">屬性須落在稀有度平衡區間；生成前會檢索避免重複</p>
        </div>
        <button type="button" onClick={() => void load()} className="rounded-xl border border-white/[0.08] px-2 py-1 text-[11px] text-[#8a8f98]">重新整理</button>
      </div>
      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}

      <div className="mb-4 grid gap-2 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3 sm:grid-cols-2 lg:grid-cols-6">
        <label className="text-[10px] text-[#8a8f98] lg:col-span-2">名稱
          <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
        </label>
        <label className="text-[10px] text-[#8a8f98]">類型
          <select value={type} onChange={(e) => setType(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]">
            <option value="武器">武器</option>
            <option value="防具">防具</option>
            <option value="消耗品">消耗品</option>
          </select>
        </label>
        <label className="text-[10px] text-[#8a8f98]">稀有度
          <select value={rarity} onChange={(e) => setRarity(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]">
            <option value="common">common</option>
            <option value="uncommon">uncommon</option>
            <option value="rare">rare</option>
            <option value="epic">epic</option>
            <option value="legendary">legendary</option>
          </select>
        </label>
        <label className="text-[10px] text-[#8a8f98]">主屬性
          <input type="number" value={power} onChange={(e) => setPower(Number(e.target.value))} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
        </label>
        <label className="text-[10px] text-[#8a8f98] sm:col-span-2 lg:col-span-5">描述
          <input value={description} onChange={(e) => setDescription(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
        </label>
        <div className="flex items-end">
          <button type="button" disabled={busy || !name} onClick={() => void onCreate()} className="w-full rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40">
            新增
          </button>
        </div>
      </div>

      <div className="overflow-auto rounded-xl border border-white/[0.08]">
        <table className="w-full min-w-[520px] text-left text-[12px]">
          <thead className="bg-[#1C1C1E] text-[10px] uppercase tracking-wide text-[#8a8f98]">
            <tr>
              <th className="px-3 py-2 font-medium">名稱</th>
              <th className="px-3 py-2 font-medium">類型</th>
              <th className="px-3 py-2 font-medium">稀有度</th>
              <th className="px-3 py-2 font-medium">屬性</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-[#636366]">尚無道具</td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-t border-white/[0.06]">
                <td className="px-3 py-2">{item.name}</td>
                <td className="px-3 py-2 text-[#AEAEB2]">{item.type}</td>
                <td className="px-3 py-2 text-[#AEAEB2]">{item.rarity}</td>
                <td className="px-3 py-2 text-[#8a8f98]">{JSON.stringify(item.attributes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
