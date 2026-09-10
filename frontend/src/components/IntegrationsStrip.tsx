/**
 * IntegrationsStrip — 六服務狀態晶片（MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil）。
 * 契約：僅反映啟停／健康；不展示審計分數；點擊跳轉整合面板（顯式動作入口）。
 */
import { useMemo } from 'react';
import type { IntegrationStatus } from '../api/integrations';
import { useIntegrationsStatus } from '../hooks/useIntegrationsStatus';
import {
  GROUP_LABEL,
  INTEGRATION_META,
  INTEGRATION_ORDER,
  jumpToIntegration,
  metaOf,
  summarizeIntegrations,
  toneOf,
  type IntegrationName,
} from '../lib/integrationsUi';

type Density = 'compact' | 'comfortable' | 'board';

const TONE_CLS: Record<string, string> = {
  off: 'integ-chip is-off',
  ok: 'integ-chip is-ok',
  warn: 'integ-chip is-warn',
  err: 'integ-chip is-err',
};

function Chip({
  item,
  density,
  onFocus,
}: {
  item: IntegrationStatus | undefined;
  density: Density;
  onFocus?: (name: IntegrationName) => void;
}) {
  const name = (item?.name || '') as IntegrationName;
  const meta = metaOf(name) ?? INTEGRATION_META.memos;
  const tone = toneOf(item);
  const label = density === 'compact' ? meta.short : meta.label;
  const title = [
    meta.label,
    meta.hint,
    item?.enabled ? (item.health?.ok === false ? item.health.reason_code || '不可達' : '已啟用') : '已停用',
    item?.base_url,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <button
      type="button"
      className={TONE_CLS[tone]}
      title={title}
      style={{ ['--integ-accent' as string]: meta.accent }}
      onClick={() => {
        if (onFocus && name) onFocus(name);
        else jumpToIntegration(name || undefined);
      }}
    >
      <span className="integ-chip-glyph" aria-hidden>
        {meta.glyph}
      </span>
      <span className="integ-chip-label">{label}</span>
      {density !== 'compact' && item?.enabled && typeof item.health?.latency_ms === 'number' ? (
        <span className="integ-chip-ms">{Math.round(item.health.latency_ms)}ms</span>
      ) : null}
    </button>
  );
}

export default function IntegrationsStrip({
  items: externalItems,
  density = 'comfortable',
  showSummary = true,
  showGroups = false,
  pollMs = 12000,
  className = '',
  onFocus,
}: {
  items?: IntegrationStatus[];
  density?: Density;
  showSummary?: boolean;
  showGroups?: boolean;
  pollMs?: number;
  className?: string;
  onFocus?: (name: IntegrationName) => void;
}) {
  const hooked = useIntegrationsStatus(externalItems ? -1 : pollMs);
  const items = externalItems ?? hooked.items;
  const byName = useMemo(() => new Map(items.map((i) => [i.name, i])), [items]);
  const summary = summarizeIntegrations(items);

  const ordered = INTEGRATION_ORDER.map((name) => byName.get(name) ?? ({
    name,
    display_name: INTEGRATION_META[name].label,
    role: '',
    group: INTEGRATION_META[name].group,
    summary: INTEGRATION_META[name].hint,
    docs_url: '',
    enabled: false,
    base_url: '',
    health: { ok: true, enabled: false, reason_code: 'integration:disabled' },
  }));

  if (showGroups) {
    const groups: Array<'recall' | 'agent' | 'design'> = ['recall', 'agent', 'design'];
    return (
      <div className={`integ-strip integ-strip--grouped ${className}`.trim()}>
        {showSummary ? (
          <div className="integ-strip-sum">
            <span>
              外部整合 {summary.enabled}/{summary.total}
              {summary.degraded ? ` · ${summary.degraded} 降級` : ''}
            </span>
            <button type="button" className="integ-strip-link" onClick={() => jumpToIntegration()}>
              管理 →
            </button>
          </div>
        ) : null}
        {groups.map((g) => (
          <div key={g} className="integ-strip-group">
            <p className="integ-strip-group-h">
              {GROUP_LABEL[g].label}
              <span>{GROUP_LABEL[g].hint}</span>
            </p>
            <div className="integ-strip-row">
              {ordered
                .filter((i) => i.group === g)
                .map((item) => (
                  <Chip key={item.name} item={item} density={density} onFocus={onFocus} />
                ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={`integ-strip ${className}`.trim()}>
      {showSummary ? (
        <div className="integ-strip-sum">
          <span>
            整合 {summary.enabled}/{summary.total}
            {summary.degraded ? ` · 降級 ${summary.degraded}` : ''}
            {hooked.loading && !items.length ? ' · 同步中' : ''}
          </span>
          <button type="button" className="integ-strip-link" onClick={() => jumpToIntegration()}>
            面板
          </button>
        </div>
      ) : null}
      <div className="integ-strip-row">
        {ordered.map((item) => (
          <Chip key={item.name} item={item} density={density} onFocus={onFocus} />
        ))}
      </div>
    </div>
  );
}
