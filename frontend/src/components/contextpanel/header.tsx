/**
 * Context 面板頁首：標題、動作按鈕、偏好設定、任務選擇與壓力列。
 */
import type { ContextInsight } from '../../api/contextInsight';
import type { PluginCatalogEntry } from '../../api/plugins';
import { fmtPressure, fmtTokens, openChatContextDetail, openContextModal } from '../../lib/contextUi';
import type { TrendGranularity, TrendMode } from '../../lib/contextUi';
import { jumpToIntegrations, jumpToL0Kernel } from '../../lib/rahoUi';
import { btnCls } from './utils';

export function ContextHeader({
  embed,
  locked,
  taskId,
  traceOptions,
  data,
  stats,
  windowSize,
  showPrefs,
  onTogglePrefs,
  trendGran,
  onSelectGranularity,
  trendMode,
  onSelectMode,
  dshPlugin,
  pluginBusy,
  onTogglePlugin,
  busy,
  onRefresh,
  onSelectTask,
}: {
  embed: boolean;
  locked: boolean;
  taskId: string | null;
  traceOptions: Array<{ task_id: string; event_count: number }>;
  data: ContextInsight | null;
  stats: ContextInsight['stats'];
  windowSize: number;
  showPrefs: boolean;
  onTogglePrefs: () => void;
  trendGran: TrendGranularity;
  onSelectGranularity: (g: TrendGranularity) => void;
  trendMode: TrendMode;
  onSelectMode: (m: TrendMode) => void;
  dshPlugin: PluginCatalogEntry | null;
  pluginBusy: boolean;
  onTogglePlugin: () => void;
  busy: boolean;
  onRefresh: () => void;
  onSelectTask: (id: string | null) => void;
}) {
  return (
      <header className={embed ? 'ctx-embed-hero' : 'integ-hero'}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>{embed ? 'Context' : 'Context · 資產鏡像'}</h2>
            <p>
              {embed
                ? '本對話專屬。這裡只顯示這次用到的資料，無任務選擇器。'
                : (
                  <>
                    觀測完整鏡像（資產層只存與取；主表面在對話底部詳細區）。靈感來自{' '}
                    <a
                      href="https://github.com/bowenliang123/dsh-context"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[var(--console-accent)] hover:underline"
                    >
                      dsh-context
                    </a>
                    。對話輸入 <code className="text-[10px] text-[var(--console-sub)]">/context</code> 優先開詳細區；
                    <code className="ml-1 text-[10px] text-[var(--console-sub)]">/context peek</code> 開浮動預覽。
                  </>
                )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {!embed ? (
              <>
                <button
                  type="button"
                  className={btnCls}
                  onClick={() => openChatContextDetail(taskId)}
                  title="開啟對話底部詳細區（主表面）"
                >
                  對話詳細區
                </button>
                <button
                  type="button"
                  className={btnCls}
                  onClick={() => openContextModal(taskId)}
                  title="浮動 Peek（不離開本頁）"
                >
                  Peek
                </button>
                <button type="button" className={btnCls} onClick={jumpToL0Kernel}>
                  記憶
                </button>
                <button type="button" className={btnCls} onClick={() => jumpToIntegrations()}>
                  外部整合
                </button>
              </>
            ) : (
              <button
                type="button"
                className={btnCls}
                onClick={() => openContextModal(taskId)}
                title="浮動 Peek"
              >
                Peek
              </button>
            )}
            <button type="button" className={btnCls} onClick={onTogglePrefs}>
              設定
            </button>
            {dshPlugin ? (
              <button
                type="button"
                className={btnCls}
                disabled={pluginBusy}
                title={
                  dshPlugin.enabled
                    ? 'dsh-context 適配已啟用（可視化常駐）'
                    : '顯式啟用 dsh-context 可視化適配'
                }
                onClick={onTogglePlugin}
              >
                {dshPlugin.enabled ? 'dsh-context · 已啟用' : '啟用 dsh-context'}
              </button>
            ) : null}
            <button type="button" className={btnCls} disabled={busy} onClick={onRefresh}>
              {busy ? '更新中…' : '重新整理'}
            </button>
          </div>
        </div>
        {showPrefs ? (
          <div className="mt-3 rounded-xl border border-white/[0.08] bg-black/25 p-3">
            <p className="mb-2 text-[11px] font-medium text-[var(--console-ink)]">Context 偏好（本機）</p>
            <div className="flex flex-wrap gap-3 text-[11px] text-[var(--console-sub)]">
              <label className="flex items-center gap-2">
                趨勢粒度
                <select
                  className="rounded-lg border border-white/[0.08] bg-black/40 px-2 py-1 text-[12px] text-[var(--console-ink)]"
                  value={trendGran}
                  onChange={(e) => {
                    const g = e.target.value === 'turn' ? 'turn' : 'step';
                    onSelectGranularity(g);
                  }}
                >
                  <option value="step">Step（每次 LLM）</option>
                  <option value="turn">Turn（同 phase 合併）</option>
                </select>
              </label>
              <label className="flex items-center gap-2">
                趨勢模式
                <select
                  className="rounded-lg border border-white/[0.08] bg-black/40 px-2 py-1 text-[12px] text-[var(--console-ink)]"
                  value={trendMode}
                  onChange={(e) => {
                    const m = e.target.value === 'delta' ? 'delta' : 'total';
                    onSelectMode(m);
                  }}
                >
                  <option value="total">Total（累計組成）</option>
                  <option value="delta">Delta（逐步增減）</option>
                </select>
              </label>
            </div>
          </div>
        ) : null}
        <div className={`mt-3 flex flex-wrap items-end gap-2${embed ? ' ctx-embed-meta' : ''}`}>
          {locked ? (
            <span
              className="rounded-full border border-[color-mix(in_srgb,var(--console-green)_25%,transparent)] bg-[color-mix(in_srgb,var(--console-green)_10%,transparent)] px-2.5 py-1 font-mono text-[10px] text-[var(--console-green)]"
              data-testid="context-locked-task"
              title="已鎖定本對話任務，無選擇器、不可切換其他會話"
            >
              {taskId ? `🔒 本對話 · ${taskId.slice(0, 12)}…` : '🔒 本對話 · 尚無任務'}
            </span>
          ) : (
            <label className="block text-[10px] text-[var(--console-sub)]">
              任務
              <select
                className="mt-1 block min-w-[220px] rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px] text-[var(--console-ink)]"
                value={taskId || ''}
                onChange={(e) => {
                  onSelectTask(e.target.value || null);
                }}
                data-testid="context-task-select"
              >
                <option value="">最新軌跡</option>
                {traceOptions.map((t) => (
                  <option key={t.task_id} value={t.task_id}>
                    {t.task_id.slice(0, 12)}… · {t.event_count} 事件
                  </option>
                ))}
              </select>
            </label>
          )}
          {data?.task_id && !locked ? (
            <span className="rounded-full border border-white/[0.08] px-2.5 py-1 font-mono text-[10px] text-[var(--console-sub)]">
              {data.task_id}
            </span>
          ) : null}
          <span className="rounded-full border border-white/[0.08] px-2.5 py-1 text-[10px] text-[var(--console-sub)]">
            壓力 {fmtPressure(stats.context_pressure)} · 窗 {fmtTokens(stats.est_window_tokens)} /{' '}
            {fmtTokens(windowSize)}
          </span>
        </div>
      </header>
  );
}
