/**
 * RightPanel — OPC 6 级诊断右侧滑动面板。
 *
 * 从 TaskPage 提取 OPC 6 级闭环数据展示逻辑。
 * 默认隐藏，OPC 任务运行时自动滑入。
 */
import { useEffect, useState } from 'react';
import type { TaskProgress } from '../types';
import { OPC_PHASES, usesIndustrialStages } from '../types';
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

/** 區段標題 — 實色字重階，不用漸層字／全大寫 eyebrow */
function SectionTitle({ text, extra }: { icon?: string; text: string; extra?: React.ReactNode }) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold text-[var(--console-sub)]">
      <span>{text}</span>
      {extra}
    </h3>
  );
}

export default function RightPanel({ task, onClose }: RightPanelProps) {
  const isOPC = usesIndustrialStages(task);
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
        className={`right-panel-drawer shrink-0 overflow-hidden border-l border-[var(--console-line)] bg-[var(--console-sidebar)] transition-all duration-300 ease-in-out md:relative md:static ${
          panelOpen ? 'is-open w-80 md:w-96' : 'w-0 border-l-0'
        }`}
      >
        {task && (
          <div className="flex h-full w-80 flex-col md:w-96">
            {/* 面板标题 */}
            <div className="flex items-center justify-between border-b border-[var(--console-line)] px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-semibold text-[var(--console-ink)]">OPC 診斷</span>
                {running && (
                  <span
                    className="inline-block h-2 w-2 rounded-full bg-[var(--console-cyan)]"
                    title="執行中"
                    aria-label="執行中"
                  />
                )}
              </div>
              <button
                onClick={onClose}
                className="rounded px-2 py-0.5 text-xs text-[var(--console-faint)] hover:bg-[var(--console-dim)] hover:text-[var(--console-sub)]"
              >
                ✕
              </button>
            </div>

            {/* 状态標籤 */}
            <div className="border-b border-[var(--console-line)] px-3 py-2">
              <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium ${
                running
                  ? 'badge-glow bg-[color-mix(in_srgb,var(--console-blue)_15%,transparent)] console-status-blue ring-1 ring-blue-400/50'
                  : failed
                    ? 'bg-red-500/15 console-status-danger ring-1 ring-red-500/40'
                    : 'bg-[color-mix(in_srgb,var(--console-green)_15%,transparent)] console-status-green ring-1 ring-green-500/40'
              }`}>
                {running ? '執行中' : failed ? '失敗' : '已完成'}
                {task.status === 'completed' && task.score != null && ` · 評分 ${task.score}`}
              </span>
              {running && (
                <span className="ml-2 text-[11px] text-[var(--console-faint)]">
                  已耗時 {formatDuration(durationSec)}
                </span>
              )}
            </div>

            {/* 内容区 */}
            <div className="flex-1 overflow-y-auto px-3 py-3">
              <div className="flex flex-col gap-3">
                {/* ── 6 级阶段步骤条 ── */}
                <div className="rounded-xl border border-white/5 bg-[var(--console-card)] p-3">
                  <SectionTitle text="執行階段" />
                  <div className="flex items-start">
                    {OPC_PHASES.map((p, i) => {
                      const active = running && i === currentIdx;
                      const passed = phasePassed(i);
                      return (
                        <div key={p.key} className="flex flex-1 flex-col items-center">
                          <div className="flex w-full items-center">
                            <div className={`h-0.5 flex-1 ${i === 0 ? 'opacity-0' : passed || active ? 'bg-[var(--console-cyan)]' : 'bg-[var(--console-line)]'}`} />
                            <div
                              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold transition-colors duration-300 ${
                                failed && i === currentIdx
                                  ? 'bg-red-500/20 console-status-danger ring-1 ring-red-500/50'
                                  : passed
                                    ? 'bg-[var(--console-cyan)] text-[var(--console-accent-ink)]'
                                    : active
                                      ? 'bg-[color-mix(in_srgb,var(--console-cyan)_20%,transparent)] text-[var(--console-cyan)] ring-1 ring-[var(--console-cyan)]'
                                      : 'bg-[var(--console-dim)] text-[var(--console-faint)] ring-1 ring-[var(--console-line)]'
                              }`}
                            >
                              {failed && i === currentIdx ? '✗' : passed ? '✓' : i + 1}
                            </div>
                            <div className={`h-0.5 flex-1 ${i === OPC_PHASES.length - 1 ? 'opacity-0' : phasePassed(i + 1) || (running && i + 1 === currentIdx) ? 'bg-[var(--console-cyan)]' : 'bg-[var(--console-line)]'}`} />
                          </div>
                          <span className={`mt-1 whitespace-nowrap text-[9px] ${
                            active ? 'font-medium text-[var(--console-cyan)]' : passed ? 'text-[var(--console-sub)]' : 'text-[var(--console-faint)]'
                          }`}>
                            {p.label}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                  {running && (
                    <p className="mt-2.5 flex items-center gap-1.5 text-[10px] text-[var(--console-faint)]">
                      <span className="inline-block h-2 w-2 shrink-0 animate-spin rounded-full border-[1.5px] border-[var(--console-cyan)] border-t-transparent" />
                      當前階段：{OPC_PHASES[currentIdx]?.label ?? task.phase}
                    </p>
                  )}
                  {failed && task.error && (
                    <p className="mt-2 rounded-lg border border-red-500/25 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)] px-2.5 py-1.5 text-[11px] console-status-danger">
                      {task.error}
                    </p>
                  )}
                </div>

                {/* ══ OPC 6 级数据展示 ══ */}
                {isOPC && task.opc_state && (
                  <>
                    {/* 第 1 级：感知 */}
                    {task.opc_state.sense && (
                      <div className="rounded-xl border border-white/5 bg-[var(--console-card)] p-3">
                        <SectionTitle
                          text="1. 感知（Sense）"
                          extra={
                            <span className="rounded-full bg-[color-mix(in_srgb,var(--console-cyan)_15%,transparent)] px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-[var(--console-cyan)]">
                              {task.opc_state.sense.tag_count} 標籤
                            </span>
                          }
                        />
                        <div className="overflow-x-auto">
                          <table className="w-full text-[10px]">
                            <thead>
                              <tr className="border-b border-[var(--console-line)] text-left text-[var(--console-faint)]">
                                <th className="pb-1.5 pr-2 font-medium">標籤</th>
                                <th className="pb-1.5 pr-2 font-medium">數值</th>
                                <th className="pb-1.5 font-medium">品質</th>
                              </tr>
                            </thead>
                            <tbody>
                              {Object.entries(task.opc_state.sense.readings).slice(0, 8).map(([name, info]) => (
                                <tr key={name} className="border-b border-[var(--console-line)] last:border-0">
                                  <td className="py-1 pr-2 font-medium text-[var(--console-ink)]">{name}</td>
                                  <td className="py-1 pr-2 font-mono text-[var(--console-sub)]">{String(info.value ?? '-')}</td>
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

                    {/* 第 2 级：預處理 */}
                    {task.opc_state.preprocess && (
                      <div className="rounded-xl border border-white/5 bg-[var(--console-card)] p-3">
                        <SectionTitle
                          text="2. 預處理"
                          extra={
                            <span className="rounded-full bg-[color-mix(in_srgb,var(--console-cyan)_15%,transparent)] px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-[var(--console-cyan)]">
                              {task.opc_state.preprocess.clean_count} 有效
                            </span>
                          }
                        />
                        <div className="grid grid-cols-3 gap-1.5">
                          <div className="rounded-lg border border-white/5 bg-[var(--console-dim)] px-2 py-1.5 text-center">
                            <p className="text-[9px] text-[var(--console-faint)]">總數</p>
                            <p className="text-sm font-semibold text-[var(--console-ink)]">{task.opc_state.preprocess.quality_report.total}</p>
                          </div>
                          <div className="rounded-lg border border-green-500/20 bg-green-500/5 px-2 py-1.5 text-center">
                            <p className="text-[9px] text-[var(--console-faint)]">良好</p>
                            <p className="text-sm font-semibold console-status-green">{task.opc_state.preprocess.quality_report.good}</p>
                          </div>
                          <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-2 py-1.5 text-center">
                            <p className="text-[9px] text-[var(--console-faint)]">不良</p>
                            <p className="text-sm font-semibold console-status-danger">{task.opc_state.preprocess.quality_report.bad}</p>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* 第 3 级：分析 */}
                    {task.opc_state.analyze && (
                      <div className="rounded-xl border border-white/5 bg-[var(--console-card)] p-3">
                        <SectionTitle
                          text="3. 分析"
                          extra={
                            <span className="rounded-full bg-[color-mix(in_srgb,var(--console-cyan)_15%,transparent)] px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-[var(--console-cyan)]">
                              {task.opc_state.analyze.violations.length > 0 ? `${task.opc_state.analyze.violations.length} 违规` : '无违规'}
                            </span>
                          }
                        />
                        <div className="mb-2 grid grid-cols-4 gap-1">
                          {(['min', 'max', 'avg', 'std'] as const).map((key) => (
                            <div key={key} className="rounded-md border border-white/5 bg-[var(--console-dim)] px-1.5 py-1 text-center">
                              <p className="text-[8px] uppercase text-[var(--console-faint)]">{key}</p>
                              <p className="text-[11px] font-semibold text-[var(--console-ink)]">{task.opc_state!.analyze!.stats[key].toFixed(1)}</p>
                            </div>
                          ))}
                        </div>
                        {task.opc_state.analyze.violations.length > 0 && (
                          <div className="space-y-1">
                            {task.opc_state.analyze.violations.slice(0, 3).map((v, i) => (
                              <div key={i} className={`rounded-md border px-2 py-1 text-[10px] ${
                                v.severity === 'critical' ? 'border-red-500/30 bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)]' : 'border-yellow-500/30 bg-yellow-500/10'
                              }`}>
                                <span className="font-medium text-[var(--console-ink)]">{v.tag}</span>
                                <span className="ml-1 font-mono text-[var(--console-sub)]">{v.value}</span>
                                <span className="ml-1 text-[var(--console-faint)]">（阈值 {v.threshold}）</span>
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
                          text="4. 诊断"
                          extra={
                            <span className={`rounded-full px-1.5 py-0.5 text-[9px] font-medium normal-case tracking-normal ${
                              task.opc_state.diagnose.anomaly_detected ? 'bg-red-500/20 console-status-danger' : 'bg-green-500/20 console-status-green'
                            }`}>
                              {task.opc_state.diagnose.anomaly_detected ? '异常' : '✅ 正常'}
                            </span>
                          }
                        />
                        <div className="space-y-1.5 text-[11px]">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[var(--console-faint)]">嚴重程度：</span>
                            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                              task.opc_state.diagnose.severity === 'critical' ? 'bg-red-500/20 console-status-danger' :
                              task.opc_state.diagnose.severity === 'warning' ? 'bg-yellow-500/20 text-yellow-300' :
                              'bg-green-500/20 console-status-green'
                            }`}>
                              {task.opc_state.diagnose.severity}
                            </span>
                          </div>
                          {task.opc_state.diagnose.root_cause && (
                            <p className="rounded-md border border-white/5 bg-[var(--console-dim)] px-2 py-1.5 leading-relaxed text-[var(--console-sub)]">
                              {task.opc_state.diagnose.root_cause}
                            </p>
                          )}
                        </div>
                      </div>
                    )}

                    {/* 第 5 级：决策 */}
                    {task.opc_state.decide && (
                      <div className="rounded-xl border border-white/5 bg-[var(--console-card)] p-3">
                        <SectionTitle
                          text="5. 决策"
                          extra={
                            <span className="rounded-full bg-[color-mix(in_srgb,var(--console-cyan)_15%,transparent)] px-1.5 py-0.5 text-[9px] font-normal normal-case tracking-normal text-[var(--console-cyan)]">
                              {task.opc_state.decide.decisions.length} 个决策
                            </span>
                          }
                        />
                        {task.opc_state.decide.decisions.length > 0 ? (
                          <div className="space-y-1.5">
                            {task.opc_state.decide.decisions.slice(0, 5).map((d, i) => (
                              <div key={i} className="rounded-lg border border-white/5 bg-[var(--console-dim)] px-2.5 py-2">
                                <div className="flex items-center gap-1.5 mb-1">
                                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--console-cyan)_15%,transparent)] text-[10px] font-semibold text-[var(--console-cyan)]">{d.order ?? i + 1}</span>
                                  <span className="text-[11px] font-medium text-[var(--console-ink)]">{d.tag_name}</span>
                                  <span className="text-[11px] font-mono text-[var(--console-faint)]">→ {d.value}</span>
                                  <span className={`ml-auto rounded-full px-1.5 py-0.5 text-[9px] font-medium ${
                                    d.priority === 'critical' ? 'bg-red-500/20 console-status-danger' :
                                    d.priority === 'high' ? 'bg-orange-500/20 text-orange-300' :
                                    d.priority === 'medium' ? 'bg-yellow-500/20 text-yellow-300' :
                                    'bg-green-500/20 console-status-green'
                                  }`}>
                                    {d.priority}
                                  </span>
                                </div>
                                <span className="text-[10px] text-[var(--console-faint)]">{d.reason}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[11px] text-[var(--console-faint)]">無需執行控制動作</p>
                        )}
                      </div>
                    )}

                    {/* 第 6 级：执行 */}
                    {task.opc_state.act && (
                      <div className="rounded-xl border border-white/5 bg-[var(--console-card)] p-3">
                        <SectionTitle
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
                                <span className="font-medium text-[var(--console-ink)]">{a.tag_name}</span>
                                {a.written_value != null && (
                                  <span className="font-mono text-[var(--console-faint)]">→ {a.written_value}</span>
                                )}
                                <span className="ml-auto text-[var(--console-faint)]">{a.message ?? (a.success ? '寫入成功' : '写入失敗')}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[11px] text-[var(--console-faint)]">無需執行控制動作</p>
                        )}
                      </div>
                    )}
                  </>
                )}

                {/* 非 OPC 任務提示 */}
                {!isOPC && (
                  <div className="rounded-xl border border-[var(--console-line)] bg-[var(--console-card)] p-4 text-center">
                    <p className="text-xs text-[var(--console-faint)]">
                      此任務非 OPC 模式，請在輸入框開啟 OPC 以查看六階段診斷資料。
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