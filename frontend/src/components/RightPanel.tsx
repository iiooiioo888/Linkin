/**
 * RightPanel — OPC 6 级诊断右侧滑动面板。
 *
 * 从 TaskPage 提取 OPC 6 级闭环数据展示逻辑。
 * 默认隐藏，OPC 任务运行时自动滑入。
 */
import { useEffect, useState } from 'react';
import type { TaskProgress } from '../types';
import { OPC_PHASES } from '../types';
import { phaseIndex } from './TaskPanel';

interface RightPanelProps {
  task: TaskProgress | null;
  onClose: () => void;
}

/** 耗时格式化 */
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  if (m < 60) return `${m} 分 ${s} 秒`;
  return `${Math.floor(m / 60)} 时 ${m % 60} 分`;
}

/** 区段标题 */
function SectionTitle({ icon, text, extra }: { icon?: string; text: string; extra?: React.ReactNode }) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
      {icon && <span className="text-xs">{icon}</span>}
      <span className="bg-gradient-to-r from-gray-200 to-gray-400 bg-clip-text text-transparent">{text}</span>
      {extra}
    </h3>
  );
}

export default function RightPanel({ task, onClose }: RightPanelProps) {
  const isOPC = task?.resolved_path === 'opc';
  const running = task?.status === 'running' || task?.status === 'pending';
  const failed = task?.status === 'failed';
  const currentIdx = task ? phaseIndex(OPC_PHASES, task.phase) : -1;

  // 耗时计时
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  const durationSec = task?.created_at ? Math.max(0, Math.floor(now / 1000 - task.created_at)) : 0;

  const phasePassed = (i: number) =>
    failed ? i < currentIdx : i < currentIdx || (!running && i <= currentIdx);

  // 面板宽度动画
  const panelOpen = task !== null;

  return (
    <>
      {/* 遮罩层（移动端） */}
      {panelOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={`right-panel-drawer shrink-0 overflow-hidden border-l border-gray-800 bg-gray-900 transition-all duration-300 ease-in-out md:relative md:static ${
          panelOpen ? 'is-open w-80 md:w-96' : 'w-0 border-l-0'
        }`}
      >
        {task && (
          <div className="flex h-full w-80 flex-col md:w-96">
            {/* 面板标题 */}
            <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-sm">🏭</span>
                <span className="text-xs font-semibold text-gray-200">OPC 诊断</span>
                {running && (
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-cyan-400" />
                )}
              </div>
              <button
                onClick={onClose}
                className="rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-800 hover:text-gray-300"
              >
                ✕
              </button>
            </div>

            {/* 状态标签 */}
            <div className="border-b border-gray-800 px-3 py-2">
              <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium ${
                running
                  ? 'badge-glow bg-[color-mix(in_srgb,var(--console-blue)_15%,transparent)] console-status-blue ring-1 ring-blue-400/50'
                  : failed
                    ? 'bg-red-500/15 console-status-danger ring-1 ring-red-500/40'
                    : 'bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] console-status-green ring-1 ring-green-500/40'
              }`}>
                {running ? '执行中' : failed ? '失败' : '已完成'}
                {task.status === 'completed' && task.score != null && ` · 评分 ${task.score}`}
              </span>
              {running && (
                <span className="ml-2 text-[11px] text-gray-500">
                  已耗时 {formatDuration(durationSec)}
                </span>
              )}
            </div>

            {/* 内容区 */}
            <div className="flex-1 overflow-y-auto px-3 py-3">
              <div className="flex flex-col gap-3">
                {/* ── 6 级阶段步骤条 ── */}
                <div className="rounded-xl border border-white/5 bg-gray-900/80 p-3">
                  <SectionTitle icon="🧭" text="执行阶段" />
                  <div className="flex items-start">
                    {OPC_PHASES.map((p, i) => {
                      const active = running && i === currentIdx;
                      const passed = phasePassed(i);
                      return (
                        <div key={p.key} className="flex flex-1 flex-col items-center">
                          <div className="flex w-full items-center">
                            <div className={`h-0.5 flex-1 ${i === 0 ? 'opacity-0' : passed || active ? 'bg-cyan-500/70' : 'bg-gray-700/60'}`} />
                            <div
                              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold transition-colors duration-300 ${
                                failed && i === currentIdx
                                  ? 'bg-red-500/20 console-status-danger ring-1 ring-red-500/50'
                                  : passed
                                    ? 'bg-cyan-500 text-white shadow-[0_0_6px_rgba(6,182,212,0.4)]'
                                    : active
                                      ? 'node-ring bg-cyan-500/20 text-cyan-200 ring-1 ring-cyan-400/70'
                                      : 'bg-gray-800 text-gray-500 ring-1 ring-gray-700'
                              }`}
                            >
                              {failed && i === currentIdx ? '✗' : passed ? '✓' : i + 1}
                            </div>
                            <div className={`h-0.5 flex-1 ${i === OPC_PHASES.length - 1 ? 'opacity-0' : phasePassed(i + 1) || (running && i + 1 === currentIdx) ? 'bg-cyan-500/70' : 'bg-gray-700/60'}`} />
                          </div>
                          <span className={`mt-1 whitespace-nowrap text-[9px] ${
                            active ? 'font-medium text-cyan-300' : passed ? 'text-gray-300' : 'text-gray-600'
                          }`}>
                            {p.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  {running && (
                    <p className="mt-2.5 flex items-center gap-1.5 text-[10px] text-gray-500">
                      <span className="inline-block h-2 w-2 shrink-0 animate-spin rounded-full border-[1.5px] border-cyan-400 border-t-transparent" />
                      当前阶段：{OPC_PHASES[currentIdx]?.label ?? task.phase}
                    </p>
                  )}
                  {failed && task.error && (
                    <p className="mt-2 rounded-lg border border-red-500/25 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-2.5 py-1.5 text-[11px] console-status-danger">
                      ⚠️ {task.error}
                    </p>
                  )}
                </div>

                {/* ══ OPC 6 级数据展示 ══ */}
                {isOPC && task.opc_state && (
                  <>
                    {/* 第 1 级：感知 */}
                    {task.opc_state.sense && (
                      <div className="rounded-xl border border-white/5 bg-gray-900/80 p-3">
                        <SectionTitle
                          icon="📡"
                          text="1. 感知（Sense）"
                          extra={
                            <span className="rounded-full bg-cyan-500/15 px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-cyan-300">
                              {task.opc_state.sense.tag_count} 标签
                            </span>
                          }
                        />
                        <div className="overflow-x-auto">
                          <table className="w-full text-[10px]">
                            <thead>
                              <tr className="border-b border-gray-700/50 text-left text-gray-500">
                                <th className="pb-1.5 pr-2 font-medium">标签</th>
                                <th className="pb-1.5 pr-2 font-medium">数值</th>
                                <th className="pb-1.5 font-medium">品质</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(task.opc_state.sense.readings).slice(0, 8).map(([name, info]) => (
                                <tr key={name} className="border-b border-gray-800/50 last:border-0">
                                  <td className="py-1 pr-2 font-medium text-gray-200">{name}</td>
                                  <td className="py-1 pr-2 font-mono text-gray-300">{String(info.value ?? '-')}</td>
                                  <td className="py-1">
                                    <span className={`rounded px-1 py-0.5 text-[9px] ${
                                      String(info.quality ?? 'Good') === 'Good' ? 'bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] console-status-green' : 'bg-yellow-500/15 text-yellow-300'
                                    }`}>
                                      {String(info.quality ?? 'Good')}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* 第 2 级：预處理 */}
                    {task.opc_state.preprocess && (
                      <div className="rounded-xl border border-white/5 bg-gray-900/80 p-3">
                        <SectionTitle
                          icon="🧹"
                          text="2. 预處理"
                          extra={
                            <span className="rounded-full bg-cyan-500/15 px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-cyan-300">
                              {task.opc_state.preprocess.clean_count} 有效
                            </span>
                          }
                        />
                        <div className="grid grid-cols-3 gap-1.5">
                          <div className="rounded-lg border border-white/5 bg-gray-800/40 px-2 py-1.5 text-center">
                            <p className="text-[9px] text-gray-500">总数</p>
                            <p className="text-sm font-semibold text-gray-100">{task.opc_state.preprocess.quality_report.total}</p>
                          </div>
                          <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-2 py-1.5 text-center">
                            <p className="text-[9px] text-gray-500">良好</p>
                            <p className="text-sm font-semibold console-status-green">{task.opc_state.preprocess.quality_report.good}</p>
                          </div>
                          <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-2 py-1.5 text-center">
                            <p className="text-[9px] text-gray-500">不良</p>
                            <p className="text-sm font-semibold console-status-danger">{task.opc_state.preprocess.quality_report.bad}</p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* 第 3 级：分析 */}
                    {task.opc_state.analyze && (
                      <div className="rounded-xl border border-white/5 bg-gray-900/80 p-3">
                        <SectionTitle
                          icon="📊"
                          text="3. 分析"
                          extra={
                            <span className="rounded-full bg-cyan-500/15 px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-cyan-300">
                              {task.opc_state.analyze.violations.length > 0 ? `${task.opc_state.analyze.violations.length} 违规` : '无违规'}
                            </span>
                          }
                        />
                        <div className="mb-2 grid grid-cols-4 gap-1">
                          {(['min', 'max', 'avg', 'std'] as const).map((key) => (
                            <div key={key} className="rounded-md border border-white/5 bg-gray-800/40 px-1.5 py-1 text-center">
                              <p className="text-[8px] uppercase text-gray-500">{key}</p>
                              <p className="text-[11px] font-semibold text-gray-200">{task.opc_state!.analyze!.stats[key].toFixed(1)}</p>
                            </div>
                          ))}
                        </div>
                        {task.opc_state.analyze.violations.length > 0 && (
                          <div className="space-y-1">
                            {task.opc_state.analyze.violations.slice(0, 3).map((v, i) => (
                              <div key={i} className={`rounded-md border px-2 py-1 text-[10px] ${
                                v.severity === 'critical' ? 'border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)]' : 'border-yellow-500/30 bg-yellow-500/10'
                              }`}>
                                <span className="font-medium text-gray-200">{v.tag}</span>
                                <span className="ml-1 font-mono text-gray-300">{v.value}</span>
                                <span className="ml-1 text-gray-500">（阈值 {v.threshold}）</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 第 4 级：诊断 */}
                    {task.opc_state.diagnose && (
                      <div className={`rounded-xl border p-3 ${
                        task.opc_state.diagnose.anomaly_detected
                          ? 'border-red-500/25 bg-red-500/5'
                          : 'border-green-500/25 bg-green-500/5'
                      }`}>
                        <SectionTitle
                          icon="🔍"
                          text="4. 诊断"
                          extra={
                            <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium normal-case tracking-normal ${
                              task.opc_state.diagnose.anomaly_detected ? 'bg-red-500/20 console-status-danger' : 'bg-green-500/20 console-status-green'
                            }`}>
                              {task.opc_state.diagnose.anomaly_detected ? '⚠️ 异常' : '✅ 正常'}
                            </span>
                          }
                        />
                        <div className="space-y-1.5 text-[11px]">
                          <div className="flex items-center gap-1.5">
                            <span className="text-gray-500">严重程度：</span>
                            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                              task.opc_state.diagnose.severity === 'critical' ? 'bg-red-500/20 console-status-danger' :
                              task.opc_state.diagnose.severity === 'warning' ? 'bg-yellow-500/20 text-yellow-300' :
                              'bg-green-500/20 console-status-green'
                            }`}>
                              {task.opc_state.diagnose.severity}
                            </span>
                          </div>
                          {task.opc_state.diagnose.root_cause && (
                            <p className="rounded-md border border-white/5 bg-gray-800/40 px-2 py-1.5 leading-relaxed text-gray-300">
                              {task.opc_state.diagnose.root_cause}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 第 5 级：决策 */}
                    {task.opc_state.decide && (
                      <div className="rounded-xl border border-white/5 bg-gray-900/80 p-3">
                        <SectionTitle
                          icon="🧠"
                          text="5. 决策"
                          extra={
                            <span className="rounded-full bg-cyan-500/15 px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-cyan-300">
                              {task.opc_state.decide.decisions.length} 个决策
                            </span>
                          }
                        />
                        {task.opc_state.decide.decisions.length > 0 ? (
                          <div className="space-y-1.5">
                            {task.opc_state.decide.decisions.slice(0, 5).map((d, i) => (
                              <div key={i} className="rounded-lg border border-white/5 bg-gray-800/40 px-2.5 py-2">
                                <div className="flex items-center gap-1.5 mb-1">
                                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-cyan-500/15 text-[10px] font-semibold text-cyan-300">{d.order ?? i + 1}</span>
                                  <span className="text-[11px] font-medium text-gray-200">{d.tag_name}</span>
                                  <span className="text-[11px] font-mono text-gray-400">→ {d.value}</span>
                                  <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[9px] font-medium ${
                                    d.priority === 'critical' ? 'bg-red-500/20 console-status-danger' :
                                    d.priority === 'high' ? 'bg-orange-500/20 text-orange-300' :
                                    d.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-300' :
                                    'bg-green-500/20 console-status-green'
                                  }`}>
                                    {d.priority}
                                  </span>
                                </div>
                                <span className="text-[10px] text-gray-500">{d.reason}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[11px] text-gray-500">无需执行控制动作</p>
                        )}
                      </div>
                    )}

                    {/* 第 6 级：执行 */}
                    {task.opc_state.act && (
                      <div className="rounded-xl border border-white/5 bg-gray-900/80 p-3">
                        <SectionTitle
                          icon="⚡"
                          text="6. 执行"
                          extra={
                            task.opc_state.act.action_count > 0 && (
                              <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal ${
                                task.opc_state.act.success_count === task.opc_state.act.action_count
                                  ? 'bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] console-status-green'
                                  : 'bg-yellow-500/15 text-yellow-300'
                              }`}>
                                {task.opc_state.act.success_count}/{task.opc_state.act.action_count} 成功
                              </span>
                            )
                          }
                        />
                        {task.opc_state.act.actions.length > 0 ? (
                          <div className="space-y-1">
                            {task.opc_state.act.actions.map((a, i) => (
                              <div key={i} className={`flex items-center gap-2 rounded-md border px-2 py-1.5 text-[10px] ${
                                a.success ? 'border-green-500/20 bg-green-500/5' : 'border-red-500/20 bg-red-500/5'
                              }`}>
                                <span>{a.success ? '✅' : '❌'}</span>
                                <span className="font-medium text-gray-200">{a.tag_name}</span>
                                {a.written_value != null && (
                                  <span className="font-mono text-gray-400">→ {a.written_value}</span>
                                )}
                                <span className="ml-auto text-gray-500">{a.message ?? (a.success ? '写入成功' : '写入失败')}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[11px] text-gray-500">无需执行控制动作</p>
                        )}
                      </div>
                    )}
                  </>
                )}

                {/* 非 OPC 任务提示 */}
                {!isOPC && (
                  <div className="rounded-xl border border-white/5 bg-gray-900/80 p-4 text-center">
                    <p className="text-sm text-gray-400">🏭</p>
                    <p className="mt-2 text-xs text-gray-500">
                      此任务非 OPC 模式，请在输入框中开启 OPC 模式以查看 6 级诊断数据。
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}