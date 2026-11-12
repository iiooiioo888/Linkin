/**
 * 右側資訊欄：系統狀態、近期活動與快速操作。
 */

import type { OptimizationMonitorData } from '../../types';
import {
  ConsoleColumnScroll,
  ConsoleRightRail,
  ConsoleSnippetList,
  consoleLayout,
} from '../ui/ConsoleLayout';

export function RightRail({
  systemHealthy,
  activeCount,
  hitPct,
  recentCycles,
  quickActions,
}: {
  systemHealthy: boolean;
  activeCount: number;
  hitPct: number;
  recentCycles: NonNullable<OptimizationMonitorData['reflection_trace']>['recent_cycles'];
  quickActions: Array<{ label: string; href: string }>;
}) {
  return (
        <ConsoleRightRail>
          <div className="shrink-0 border-b border-[var(--console-line)] px-4 py-3">
            <p className="text-[11px] font-semibold text-[var(--console-ink)]">側欄</p>
          </div>
          <ConsoleColumnScroll>
            <div className={consoleLayout.sectionStack}>
              <ConsoleSnippetList title="系統狀態">
                <div className={consoleLayout.snippetRow}>
                  <span className="inline-flex items-center gap-1.5">
                    <span className={systemHealthy ? 'apple-dot apple-dot--ok' : 'apple-dot apple-dot--warn'} />
                    運行時
                  </span>
                  <span className={systemHealthy ? 'console-status-green' : 'console-status-amber'}>
                    {systemHealthy ? '正常' : '注意'}
                  </span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>優化啟用</span>
                  <span className="console-status-accent">{activeCount}</span>
                </div>
                <div className={consoleLayout.snippetRow}>
                  <span>快取命中</span>
                  <span className="console-status-green">{hitPct}%</span>
                </div>
              </ConsoleSnippetList>

              <ConsoleSnippetList title="近期活動">
                {recentCycles.length === 0 ? (
                  <p className="px-1 py-2 text-[10px] text-[var(--console-faint)]">尚無反思軌跡</p>
                ) : (
                  recentCycles.slice(0, 5).map((cycle) => (
                    <div key={cycle.task_id} className={consoleLayout.snippetRow}>
                      <span className="truncate font-mono text-[10px] text-[var(--console-sub)]">
                        {cycle.task_id.slice(0, 10)}…
                      </span>
                      <span className="shrink-0 text-[10px] console-status-blue">
                        {cycle.iterations} 輪
                      </span>
                    </div>
                  ))
                )}
              </ConsoleSnippetList>

              <ConsoleSnippetList title="快速操作">
                <div className="grid grid-cols-2 gap-2 p-2">
                  {quickActions.map((action) => (
                    <a
                      key={action.href}
                      href={action.href}
                      className="rounded-md border border-[var(--console-line)] bg-[var(--console-card-elevated)] px-2 py-2 text-center text-[10px] font-medium text-[var(--console-sub)] transition-colors hover:border-[color-mix(in_srgb,var(--console-accent)_35%,transparent)] hover:text-[var(--console-ink)]"
                    >
                      {action.label}
                    </a>
                  ))}
                </div>
              </ConsoleSnippetList>
            </div>
          </ConsoleColumnScroll>
        </ConsoleRightRail>
  );
}
