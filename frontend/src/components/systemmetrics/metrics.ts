/**
 * 系統指標列型別與資料轉換（純函式，無 JSX）。
 */

import type { OptimizationMonitorData } from '../../types';

export type MetricRow = {
  name: string;
  desc: string;
  value: string;
  unit: string;
  pct: number | null;
  status: 'good' | 'warn' | 'idle' | 'info';
  statusLabel: string;
};

export function buildMetricRows(data: OptimizationMonitorData | null): MetricRow[] {
  if (!data) return [];
  const cache = data.llm_cache;
  const hitPct = Math.round((cache?.hit_rate ?? 0) * 100);
  const routing = data.routing_feedback;
  const reflection = data.reflection;
  const userFb = data.user_feedback;
  const trace = data.trace;
  const sys = data.system_stats;
  const edge = data.edge_cache ?? data.opc_edge;
  const reflectionTrace = data.reflection_trace;
  const satisfaction = Math.round((userFb?.satisfaction_rate ?? 0) * 100);

  return [
    {
      name: 'LLM 快取命中率',
      desc: '分層快取（精確 + 語義）',
      value: String(hitPct),
      unit: '%',
      pct: hitPct,
      status: hitPct >= 30 ? 'good' : hitPct > 0 ? 'info' : 'idle',
      statusLabel: hitPct >= 30 ? '良好' : hitPct > 0 ? '累積中' : '待命中',
    },
    {
      name: '反思通過門檻',
      desc: '動態閾值（依任務複雜度調整）',
      value: String(reflection.pass_threshold ?? 8),
      unit: '分',
      pct: ((reflection.pass_threshold ?? 8) / 10) * 100,
      status: 'info',
      statusLabel: '動態',
    },
    {
      name: '路由自適應門檻',
      desc: 'simple / company 字數分界',
      value: String(routing?.adaptive_length_threshold ?? '—'),
      unit: '字',
      pct: null,
      status: (routing?.total ?? 0) >= 10 ? 'good' : 'idle',
      statusLabel: (routing?.total ?? 0) >= 10 ? '學習中' : '樣本不足',
    },
    {
      name: '用戶滿意度',
      desc: '顯式反饋閉環',
      value: String(satisfaction),
      unit: '%',
      pct: satisfaction,
      status: satisfaction >= 70 ? 'good' : satisfaction > 0 ? 'warn' : 'idle',
      statusLabel: satisfaction >= 70 ? '良好' : satisfaction > 0 ? '待改善' : '無樣本',
    },
    {
      name: '任務成功率',
      desc: '運行時任務完成率',
      value: String(sys?.success_rate ?? 0),
      unit: '%',
      pct: sys?.success_rate ?? 0,
      status: (sys?.success_rate ?? 0) >= 80 ? 'good' : (sys?.success_rate ?? 0) > 0 ? 'warn' : 'idle',
      statusLabel: `${sys?.tasks_completed ?? 0}/${sys?.tasks_total ?? 0}`,
    },
    {
      name: '全鏈路 Trace',
      desc: '節點事件軌跡筆數',
      value: String(trace?.trace_count ?? 0),
      unit: '筆',
      pct: null,
      status: (trace?.trace_count ?? 0) > 0 ? 'good' : 'idle',
      statusLabel: (trace?.trace_count ?? 0) > 0 ? '記錄中' : '尚無',
    },
    {
      name: '分層快取',
      desc: 'LLM 精確 + 語義快取',
      value: String(edge?.entry_count ?? 0),
      unit: `/${edge?.max_size ?? 512}`,
      pct: edge?.max_size ? ((edge?.entry_count ?? 0) / edge.max_size) * 100 : null,
      status: (edge?.hit_rate ?? 0) >= 0.3 ? 'good' : (edge?.entry_count ?? 0) > 0 ? 'info' : 'idle',
      statusLabel: `命中 ${Math.round((edge?.hit_rate ?? 0) * 100)}%`,
    },
    {
      name: '反思迭代上限',
      desc: '早停 + 最大輪次',
      value: String(reflection.max_iterations ?? 3),
      unit: '輪',
      pct: null,
      status: 'info',
      statusLabel: `Δ${reflection.min_score_improvement ?? 0.5}`,
    },
    {
      name: '反思鏈路均耗時',
      desc: 'evaluate + reflect + improve（Trace 彙總）',
      value:
        reflectionTrace?.avg_loop_duration_ms != null
          ? String(Math.round(reflectionTrace.avg_loop_duration_ms))
          : '—',
      unit: reflectionTrace?.avg_loop_duration_ms != null ? 'ms' : '',
      pct: null,
      status: (reflectionTrace?.tasks_analyzed ?? 0) > 0 ? 'info' : 'idle',
      statusLabel:
        reflectionTrace?.tasks_analyzed != null && reflectionTrace.tasks_analyzed > 0
          ? `${reflectionTrace.tasks_analyzed} 任務`
          : '尚無軌跡',
    },
    {
      name: '反思改進幅度',
      desc: '首輪與末輪評分差（Trace 彙總）',
      value:
        reflectionTrace?.avg_score_delta != null
          ? String(reflectionTrace.avg_score_delta)
          : '—',
      unit: reflectionTrace?.avg_score_delta != null ? '分' : '',
      pct: null,
      status:
        (reflectionTrace?.avg_score_delta ?? 0) >= 0.5
          ? 'good'
          : (reflectionTrace?.tasks_analyzed ?? 0) > 0
            ? 'warn'
            : 'idle',
      statusLabel:
        reflectionTrace?.improvement_rate_pct != null
          ? `提升率 ${reflectionTrace.improvement_rate_pct}%`
          : '—',
    },
  ];
}
