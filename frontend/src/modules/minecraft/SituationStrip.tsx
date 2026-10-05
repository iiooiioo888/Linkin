/**
 * 四維情境快照 — 市況／經濟／地土／玩家。
 */
import { useCallback, useState } from 'react';
import { fetchMinecraftSituation, type MinecraftSituationSnapshot } from '../../api/linkin';
import { formatTs, statusLabel, useVisibilityPoll } from './monitor/shared';
import './minecraft.css';

const DIM_LABELS: Record<string, string> = {
  market: '市況',
  economy: '經濟',
  land: '地土',
  players: '玩家',
};

function DimCell({
  keyName,
  block,
}: {
  keyName: string;
  block?: { status?: string; summary?: string; confidence?: number } | null;
}) {
  const label = DIM_LABELS[keyName] || keyName;
  const status = block?.status || '';
  const tone = status === 'ok' ? ' is-ok' : status === 'partial' ? ' is-partial' : '';
  const summary = (block?.summary || '').trim();
  return (
    <div className="mc-dim">
      <div className="mc-row__top">
        <span className="mc-dim__label">{label}</span>
        {status ? <span className={`mc-dim__status${tone}`}>{statusLabel(status)}</span> : null}
      </div>
      <p className="mc-dim__summary">{summary || '這一面還沒有觀察。'}</p>
      {typeof block?.confidence === 'number' ? (
        <div className="mc-dim__bar">
          <span>
            <i style={{ width: `${Math.round(Math.min(1, Math.max(0, block.confidence)) * 100)}%` }} />
          </span>
          <em>信心 {Math.round(block.confidence * 100)}%</em>
        </div>
      ) : null}
    </div>
  );
}

type SituationStripProps = {
  compact?: boolean;
  pollMs?: number;
  embedded?: boolean;
  /** 內嵌於總覽且另有規則面板時，隱藏簡短建議列表 */
  hideRecommendations?: boolean;
};

export default function SituationStrip({
  compact = false,
  pollMs = 15000,
  embedded = false,
  hideRecommendations = false,
}: SituationStripProps) {
  const [data, setData] = useState<MinecraftSituationSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError(null);
    try {
      const snap = await fetchMinecraftSituation();
      if (!snap || typeof snap !== 'object') {
        throw new Error('情境快照格式異常');
      }
      setData(snap);
    } catch (err) {
      setData(null);
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, pollMs);

  if (error) {
    return <p className="mc-error">情境讀取失敗：{error}</p>;
  }

  if (!data && loading) {
    return <p className="mc-empty">正在讀取情境…</p>;
  }

  if (!data) {
    return <p className="mc-empty">情境快照目前不可用。</p>;
  }

  const dims = ['market', 'economy', 'land', 'players'] as const;
  const recs = Array.isArray(data.rule_recommendations) ? data.rule_recommendations.slice(0, 3) : [];
  const hints = Array.isArray(data.hints) ? data.hints.slice(0, 4) : [];

  return (
    <div className="mc-page__inner" style={{ gap: 12, maxWidth: 'none', margin: 0 }}>
      {!embedded ? (
        <div className="mc-row__top">
          <span className="mc-panel__title">四維情境</span>
          <span className="mc-panel__hint">{loading ? '讀取中' : formatTs(data.generated_at)}</span>
          <button type="button" className="mc-btn" onClick={() => void load()} disabled={loading}>
            重新整理
          </button>
        </div>
      ) : (
        <div className="mc-row__top">
          <span className="mc-panel__hint">{loading ? '讀取中' : formatTs(data.generated_at)}</span>
          <button type="button" className="mc-btn" onClick={() => void load()} disabled={loading}>
            重新整理
          </button>
        </div>
      )}
      <div className="mc-situation">
        {dims.map((key) => (
          <DimCell key={key} keyName={key} block={data[key]} />
        ))}
      </div>
      {!compact && !hideRecommendations && recs.length ? (
        <ul className="mc-list">
          {recs.map((rec) => (
            <li key={rec.id} className="mc-row">
              <span className="mc-row__status">{rec.action_type}</span>
              <span>{rec.message}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {!compact && hints.length ? (
        <ul className="mc-list">
          {hints.map((hint, idx) => (
            <li key={`${idx}-${hint}`} className="mc-note">
              {hint}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
