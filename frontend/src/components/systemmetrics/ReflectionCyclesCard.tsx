/**
 * 反思鏈路追蹤表（輪次 · 分數 · Δ · 耗時 · 早停）。
 */

import type { OptimizationMonitorData } from '../../types';
import { ConsoleCard, ConsoleCardHeader } from '../ui/ConsoleLayout';

export function ReflectionCyclesCard({
  reflectionTrace,
}: {
  reflectionTrace: OptimizationMonitorData['reflection_trace'];
}) {
  return (
            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>反思鏈路追蹤（輪次 · 耗時 · 改進幅度）</ConsoleCardHeader>
              <table className="w-full text-left text-[12px]">
                <thead className="bg-[var(--console-card)] text-[10px] text-[var(--console-faint)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">任務</th>
                    <th className="px-3 py-2 font-medium">輪次</th>
                    <th className="px-3 py-2 font-medium">分數</th>
                    <th className="px-3 py-2 font-medium">Δ</th>
                    <th className="px-3 py-2 font-medium">反思耗時</th>
                    <th className="px-3 py-2 font-medium">狀態</th>
                  </tr>
                </thead>
                <tbody>
                  {(reflectionTrace?.recent_cycles ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-3 text-xs text-[var(--console-faint)]">
                        尚無反思軌跡，完成任務後將自動彙總。
                      </td>
                    </tr>
                  ) : (
                    reflectionTrace?.recent_cycles.map((cycle) => (
                      <tr key={cycle.task_id} className="border-t border-[var(--console-line)]">
                        <td className="px-3 py-1.5 font-mono text-[10px] text-[var(--console-sub)]">
                          {cycle.task_id.slice(0, 12)}
                          {cycle.task_id.length > 12 ? '…' : ''}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums text-[var(--console-sub)]">{cycle.iterations}</td>
                        <td className="px-3 py-1.5 tabular-nums text-[var(--console-sub)]">
                          {cycle.score_start != null && cycle.score_end != null
                            ? `${cycle.score_start} → ${cycle.score_end}`
                            : '—'}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums console-status-blue">
                          {cycle.score_delta != null ? `+${cycle.score_delta}` : '—'}
                        </td>
                        <td className="px-3 py-1.5 tabular-nums text-[var(--console-sub)]">
                          {cycle.loop_duration_ms > 0 ? `${Math.round(cycle.loop_duration_ms)}ms` : '—'}
                        </td>
                        <td className="px-3 py-1.5">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] ${
                              cycle.early_stop
                                ? 'console-status-amber bg-[color-mix(in_srgb,var(--console-amber)_15%,transparent)]'
                                : 'console-status-green bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)]'
                            }`}
                          >
                            {cycle.early_stop ? '早停' : '完成'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </ConsoleCard>
  );
}
