/**
 * ItemPanel — 道具庫表格與新增表單。
 */
import { useCallback, useEffect, useState } from 'react';
import { createItem, deleteItem, fetchItems, type Item } from '../../api/linkin';
import { itemTileUri } from '../../lib/visualCards';
import MediaGallery, { VisualThumb } from '../../components/media/MediaGallery';
import { mcLabel } from './localeRegions';
import PendingWorldIntentsBanner from './PendingWorldIntentsBanner';
import { McHeader, McPage, McPanel } from './McChrome';

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

  const onDelete = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      await deleteItem(id);
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
        title="道具"
        lead="屬性要落在稀有度區間。新增前會先查既有道具，避免重複。"
        aside={<button type="button" onClick={() => void load()} className="mc-btn">重新整理</button>}
      />
      <div className="mc-workspace">
      <PendingWorldIntentsBanner kind="item" compact />
      {error && <p className="mc-error">{error}</p>}

      {items.length > 0 && (
        <div className="mb-4">
          <MediaGallery
            layout="mosaic"
            filter
            items={items.map((item, index) => ({
              src: itemTileUri(item.name, item.rarity, item.type),
              caption: `${item.name} · ${mcLabel(item.rarity)}`,
              alt: item.name,
              tags: `${item.type},${item.rarity}`,
              size: item.rarity === 'legendary' || item.rarity === 'epic' ? 'large' : index % 5 === 0 ? 'large' : 'small',
            }))}
          />
        </div>
      )}

      <McPanel title="新增道具" hint="屬性會對照稀有度">
        <div className="mc-form">
          <label>名稱
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>類型
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="武器">武器</option>
              <option value="防具">防具</option>
              <option value="消耗品">消耗品</option>
            </select>
          </label>
          <label>稀有度
            <select value={rarity} onChange={(e) => setRarity(e.target.value)}>
              <option value="common">普通</option>
              <option value="uncommon">優良</option>
              <option value="rare">稀有</option>
              <option value="epic">史詩</option>
              <option value="legendary">傳說</option>
            </select>
          </label>
          <label>主屬性
            <input type="number" value={power} onChange={(e) => setPower(Number(e.target.value))} />
          </label>
          <label>描述
            <input value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <div>
            <button type="button" disabled={busy || !name} onClick={() => void onCreate()} className="mc-btn is-primary">
              {busy ? '新增中' : '新增'}
            </button>
          </div>
        </div>
      </McPanel>

      <div className="mc-table-wrap">
        <table>
          <thead>
            <tr>
              <th>名稱</th>
              <th>類型</th>
              <th>稀有度</th>
              <th>屬性</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="mc-empty">還沒有道具。</td>
              </tr>
            )}
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <span className="inline-flex items-center gap-2">
                    <VisualThumb src={itemTileUri(item.name, item.rarity, item.type)} alt={item.name} className="h-8 w-8" />
                    {item.name}
                  </span>
                </td>
                <td>{item.type}</td>
                <td>{mcLabel(item.rarity)}</td>
                <td>
                  {item.attributes && Object.keys(item.attributes).length
                    ? Object.entries(item.attributes).map(([key, value]) => `${key} ${String(value)}`).join(' · ')
                    : '無附加屬性'}
                </td>
                <td>
                  <button type="button" disabled={busy} onClick={() => void onDelete(item.id)} className="mc-danger">
                    刪除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      </div>
    </McPage>
  );
}
