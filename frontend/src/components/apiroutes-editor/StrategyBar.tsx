/**
 * API 路由編輯器：全域分發策略列。
 */
import type { LlmConfig } from '../../api/client';
import { inputCls } from './shared';
import type { EditorStatus } from './types';

interface StrategyBarProps {
  cfg: LlmConfig | null;
  compact: boolean;
  hideList: boolean;
  strategies: Array<{ id: string; label: string }>;
  status: EditorStatus;
  handleStrategy: (strategy: string) => Promise<void>;
  handleRefresh: (routeId?: string) => Promise<void>;
}

export function StrategyBar({
  cfg,
  compact,
  hideList,
  strategies,
  status,
  handleStrategy,
  handleRefresh,
}: StrategyBarProps) {
  return (
    <div className={`grid grid-cols-1 gap-3 ${compact || hideList ? '' : 'md:grid-cols-2'}`}>
      <label className="block">
        <span className="mb-1 block text-[10px] font-semibold text-[var(--console-sub)]">
          全域分發策略
        </span>
        <select
          className={inputCls}
          value={cfg?.route_strategy || 'role_preferred'}
          onChange={(e) => void handleStrategy(e.target.value)}
        >
          {strategies.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      {!compact && !hideList && (
        <div className="flex items-end">
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={status.kind === 'busy'}
            className="w-full rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[var(--console-ink)] hover:bg-white/[0.04] disabled:opacity-50"
          >
            刷新全部模型目錄
          </button>
        </div>
      )}
    </div>
  );
}
