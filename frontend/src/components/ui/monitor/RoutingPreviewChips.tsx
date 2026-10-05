import './monitor.css';
import { useTranslation } from 'react-i18next';
import type { RoutingPreview } from '../../../types';
import { resolvedPathLabel } from '../../taskdetail/labels';

interface RoutingPreviewChipsProps {
  preview: RoutingPreview;
  compact?: boolean;
  className?: string;
}

const COST_I18N: Record<string, string> = {
  low: 'routing.costLow',
  medium: 'routing.costMedium',
  high: 'routing.costHigh',
};

/**
 * 路徑標籤 + 成本等級（低／中／高），v3 monitor 暗色金色 token；不含金額與 Token 數。
 */
export function RoutingPreviewChips({ preview, compact = false, className = '' }: RoutingPreviewChipsProps) {
  const { t } = useTranslation();
  const costKey = COST_I18N[preview.estimated_cost.level] ?? 'routing.costLow';

  return (
    <div
      className={`mon-routing-chips flex min-w-0 flex-wrap items-center justify-end gap-1 ${compact ? 'mon-routing-chips--compact' : ''} ${className}`}
      data-testid="routing-preview-chips"
    >
      <span className="mon-routing-chip mon-routing-chip--path" title={preview.path}>
        {resolvedPathLabel(preview.path)}
      </span>
      <span className="mon-routing-chip mon-routing-chip--cost" title={t('routing.costLabel')}>
        {t(costKey)}
      </span>
    </div>
  );
}
