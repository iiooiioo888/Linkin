/**
 * 運維時間軸 — 玩家、AI 主持人、管線事件合併排序。
 */
import { McPanel } from '../McChrome';
import {
  formatTs,
  gmEventDetailHref,
  opsTimelineActionLabel,
  opsTimelineKind,
  opsTimelineKindLabel,
  playerEventDetailHref,
  statusLabel,
  statusStripe,
  useOpsTimeline,
} from './shared';
import '../minecraft.css';

function OpsEventRow({ evt }: { evt: import('../../../api/linkin').MinecraftObservabilityEvent }) {
  const kind = opsTimelineKind(evt.domain);
  const stripe = statusStripe(evt.status);
  const href =
    kind === 'gm'
      ? gmEventDetailHref(evt)
      : kind === 'player'
        ? playerEventDetailHref(evt)
        : undefined;
  const linkHint =
    kind === 'gm' ? '查看主持人設定 →' : kind === 'player' ? '玩家現場 →' : '';
  const playerName = (evt.entity_refs?.player_name as string) || '';

  const inner = (
    <>
      <div className="mc-ops__meta">
        <span className="mc-ops__time">{formatTs(evt.ts)}</span>
        <span className={`mc-ops__kind mc-ops__kind--${kind}`}>{opsTimelineKindLabel(kind)}</span>
        <span className="mc-ops__action">{opsTimelineActionLabel(evt)}</span>
        <span className="mc-ops__status">{statusLabel(evt.status)}</span>
        {evt.dry_run ? <span className="mc-ops__tag">乾跑</span> : null}
        {evt.bridge_offline ? <span className="mc-ops__tag mc-ops__tag--warn">橋接離線</span> : null}
      </div>
      <p className="mc-ops__summary">
        {playerName && kind === 'player' ? <span className="mc-ops__player">{playerName} · </span> : null}
        {evt.summary || '（無摘要）'}
      </p>
      {kind === 'gm' && evt.details?.rationale ? (
        <p className="mc-ops__rationale">{String(evt.details.rationale).slice(0, 200)}</p>
      ) : null}
    </>
  );

  if (href) {
    return (
      <li className="mc-ops__item mon-task-card" data-priority={stripe}>
        <a className="mc-ops__link" href={href}>
          {inner}
          {linkHint ? <span className="mc-ops__chevron">{linkHint}</span> : null}
        </a>
      </li>
    );
  }

  return (
    <li className="mc-ops__item mon-task-card" data-priority={stripe}>
      {inner}
    </li>
  );
}

export default function OpsTimelinePanel({ limit = 40 }: { limit?: number }) {
  const { events, error, reload } = useOpsTimeline(limit);

  return (
    <McPanel
      title="運維時間軸"
      hint="玩家 · 主持人 · 管線"
      action={
        <button type="button" className="rd-btn" onClick={() => void reload()}>
          重新整理
        </button>
      }
    >
      {error ? <p className="mc-error">{error}</p> : null}
      {!error && !events.length ? (
        <p className="mc-empty">
          尚無玩家、主持人或管線事件。橋接連線後玩家動作會出現；敘事管線與 AI 主持人決策也會記錄在此。
        </p>
      ) : null}
      {events.length ? (
        <ul className="mc-ops">
          {events.map((evt) => (
            <OpsEventRow key={evt.id || `${evt.ts}-${evt.domain}`} evt={evt} />
          ))}
        </ul>
      ) : null}
    </McPanel>
  );
}
