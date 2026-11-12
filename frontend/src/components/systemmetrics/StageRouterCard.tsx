/**
 * 環節 → 模型層級對照表（P0 任務-模型匹配）。
 */

import type { OptimizationMonitorData } from '../../types';
import { ConsoleCard, ConsoleCardHeader } from '../ui/ConsoleLayout';

export function StageRouterCard({ data }: {
  data: OptimizationMonitorData | null;
}) {
  return (
            <ConsoleCard className="mt-3">
              <ConsoleCardHeader>環節 → 模型層級（P0 任務-模型匹配）</ConsoleCardHeader>
              <table className="w-full text-left text-[12px]">
                <thead className="bg-[var(--console-card)] text-[10px] text-[var(--console-faint)]">
                  <tr>
                    <th className="px-3 py-2 font-medium">環節</th>
                    <th className="px-3 py-2 font-medium">Tier</th>
                    <th className="px-3 py-2 font-medium">模型</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(data?.stage_router ?? {}).map(([stage, info]) => (
                    <tr key={stage} className="border-t border-[var(--console-line)]">
                      <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">{stage}</td>
                      <td className="px-3 py-1.5 console-status-blue">{info.tier}</td>
                      <td className="px-3 py-1.5 font-mono text-[var(--console-sub)]">{info.model}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </ConsoleCard>
  );
}
