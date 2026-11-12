/**
 * 指標即時值／趨勢／狀態表格卡片。
 */

import { ConsoleCard } from '../ui/ConsoleLayout';
import { MiniProgressBar } from '../ui/monitor';
import type { MetricRow } from './metrics';

function statusClass(status: MetricRow['status']): string {
  switch (status) {
    case 'good':
      return 'console-status-green bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] px-1.5 py-0.5 rounded';
    case 'warn':
      return 'console-status-amber bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)] px-1.5 py-0.5 rounded';
    case 'info':
      return 'console-status-blue bg-[color-mix(in_srgb,var(--console-blue)_15%,transparent)] px-1.5 py-0.5 rounded';
    default:
      return 'bg-[var(--console-card)] text-[var(--console-faint)] px-1.5 py-0.5 rounded';
  }
}

export function MetricTable({ rows }: { rows: MetricRow[] }) {
  return (
            <ConsoleCard className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="border-b border-[var(--console-line)] text-[10px] text-[var(--console-faint)]">
                    <th className="px-3 py-2 font-medium">指標</th>
                    <th className="px-3 py-2 font-medium">即時值</th>
                    <th className="px-3 py-2 font-medium">趨勢</th>
                    <th className="px-3 py-2 font-medium">狀態</th>
                  </tr>
                </thead>
                <tbody className="px-3">
                  {rows.map((row) => (
                    <tr key={row.name} className="border-b border-[var(--console-line)] last:border-0">
                      <td className="py-2 pr-3">
                        <p className="text-xs font-medium text-[var(--console-ink)]">{row.name}</p>
                        <p className="text-[10px] text-[var(--console-faint)]">{row.desc}</p>
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs tabular-nums text-[var(--console-sub)]">
                        {row.value}
                        {row.unit ? <span className="ml-1 text-[var(--console-faint)]">{row.unit}</span> : null}
                      </td>
                      <td className="py-2 pr-3">
                        {row.pct != null ? (
                          <MiniProgressBar
                            value={row.pct}
                            good={row.status === 'good'}
                          />
                        ) : (
                          <span className="text-[10px] text-[var(--console-faint)]">—</span>
                        )}
                      </td>
                      <td className="py-2">
                        <span className={`text-[10px] ${statusClass(row.status)}`}>{row.statusLabel}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ConsoleCard>
  );
}
