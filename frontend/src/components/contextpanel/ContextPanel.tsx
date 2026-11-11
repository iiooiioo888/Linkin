/**
 * Context 面板 — 透視上下文組成、演進、壓縮、剪枝（靈感：dsh-context）。
 *
 * 表面：
 * - 主：對話底部詳細區 embed（ChatBottomPanel Context 分頁）／任務詳情 td-context
 *   → **鎖死當前對話任務**，禁止切換其他對話／全域軌跡
 * - 次：觀測 #/monitor/context[/{taskId}] 完整鏡像（可選任務）
 * - Stats／Composition／Trend／Browser／Events／File／Network／Token＆Timing
 * - 不渲染審計分數槽（C-UI-001）
 *
 * @see https://github.com/bowenliang123/dsh-context
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchTraces } from '../../api/client';
import { fetchContextInsight, type ContextEventKind, type ContextInsight } from '../../api/contextInsight';
import { fetchPlugins, togglePlugin, type PluginCatalogEntry } from '../../api/plugins';
import {
  aggregateTrendByTurn,
  jumpToContext,
  loadTrendGranularity,
  loadTrendMode,
  parseContextTaskId,
  saveTrendGranularity,
  saveTrendMode,
  type TrendGranularity,
  type TrendMode,
  type TrendRow,
} from '../../lib/contextUi';
import { TokenTimingRings } from './charts';
import { CompositionBar } from './composition';
import { ContextHeader } from './header';
import { AgentNetworkPane, BrowserPane, FileActivityPane } from './panes';
import { EventsCard, KpiGrid, TrendCard } from './sections';
import { cardCls, emptyInsightForDialog } from './utils';

export default function ContextPanel({
  taskId: taskIdProp,
  embed = false,
}: {
  /** 對話／任務詳情傳入時鎖死此 ID；embed 下禁止改選其他對話 */
  taskId?: string | null;
  /**
   * true＝對話詳細區／任務詳情：
   * - 僅顯示對應對話軌跡
   * - 無任務選擇器、不載入全域 trace 清單
   * - 無 taskId 時顯示空態（不回落 `/context` 最新軌跡）
   * - 後端若回傳其他 task_id 則拒絕顯示
   */
  embed?: boolean;
}) {
  /** embed：永遠跟 prop；觀測：可本地改選 */
  const locked = embed === true;
  const [taskId, setTaskId] = useState<string | null>(() =>
    locked ? taskIdProp ?? null : taskIdProp ?? parseContextTaskId(),
  );
  const [step, setStep] = useState<number | null>(null);
  const [data, setData] = useState<ContextInsight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [kindFilter, setKindFilter] = useState<ContextEventKind | 'all'>('all');
  const [trendMode, setTrendMode] = useState<TrendMode>(() => loadTrendMode());
  const [trendGran, setTrendGran] = useState<TrendGranularity>(() => loadTrendGranularity());
  const [showPrefs, setShowPrefs] = useState(false);
  const [traceOptions, setTraceOptions] = useState<Array<{ task_id: string; event_count: number }>>([]);
  const [dshPlugin, setDshPlugin] = useState<PluginCatalogEntry | null>(null);
  const [pluginBusy, setPluginBusy] = useState(false);

  useEffect(() => {
    void fetchPlugins()
      .then((p) => {
        const row = p.catalog.find((c) => c.plugin_id === 'dsh-context') || null;
        setDshPlugin(row);
      })
      .catch(() => setDshPlugin(null));
  }, []);

  useEffect(() => {
    if (locked) {
      setTaskId(taskIdProp ?? null);
      setStep(null);
      return;
    }
    if (taskIdProp === undefined) return;
    setTaskId(taskIdProp || null);
    setStep(null);
  }, [taskIdProp, locked]);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      // 對話詳細區：無本對話任務時不回落全域最新軌跡
      if (locked && !taskId) {
        setData(emptyInsightForDialog('本對話尚無任務軌跡。發送任務後將顯示對應 Context。'));
        return;
      }
      const insight = await fetchContextInsight({ taskId, step });
      // embed：若後端誤回其他 task，拒絕顯示（防跨對話）
      if (locked && taskId && insight.task_id && insight.task_id !== taskId) {
        setData(emptyInsightForDialog('軌跡與當前對話不符，已拒絕顯示其他會話 Context。'));
        return;
      }
      setData(insight);
      // 僅觀測允許跟隨 API 解析出的預設任務；embed 絕不跳轉其他對話
      if (!locked && insight.task_id && insight.task_id !== taskId) setTaskId(insight.task_id);
      if (insight.selected_step != null && step == null) setStep(insight.selected_step);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }, [taskId, step, locked]);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 10000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    if (locked) return;
    const onHash = () => {
      const id = parseContextTaskId();
      if (id) {
        setTaskId(id);
        setStep(null);
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, [locked]);

  useEffect(() => {
    if (locked) {
      setTraceOptions([]);
      return;
    }
    void fetchTraces(30)
      .then((r) => setTraceOptions(r.traces.map((t) => ({ task_id: t.task_id, event_count: t.event_count }))))
      .catch(() => setTraceOptions([]));
  }, [locked]);

  const stats = data?.stats ?? {};
  const windowSize = stats.context_window || 128000;
  const events = useMemo(() => {
    const rows = data?.events ?? [];
    if (kindFilter === 'all') return rows;
    return rows.filter((e) => e.kind === kindFilter);
  }, [data?.events, kindFilter]);

  const brief = data?.browser?.brief;
  const displayTrend = useMemo<TrendRow[]>(() => {
    const raw = data?.trend || [];
    return trendGran === 'turn' ? aggregateTrendByTurn(raw) : raw.map((r) => ({ ...r, member_steps: [r.step] }));
  }, [data?.trend, trendGran]);
  const selectedTrend = data?.trend?.find((t) => t.step === step);

  const selectTask = (id: string | null) => {
    setTaskId(id);
    setStep(null);
    jumpToContext(id);
  };

  const selectGranularity = (g: TrendGranularity) => {
    setTrendGran(g);
    saveTrendGranularity(g);
  };

  const selectMode = (m: TrendMode) => {
    setTrendMode(m);
    saveTrendMode(m);
  };

  const refresh = () => void load();

  const toggleDshPlugin = () => {
    if (!dshPlugin) return;
    setPluginBusy(true);
    void togglePlugin('dsh-context', !dshPlugin.enabled)
      .then((out) => {
        const row = out.catalog?.find((c) => c.plugin_id === 'dsh-context');
        if (row) setDshPlugin(row);
        else setDshPlugin({ ...dshPlugin, enabled: !dshPlugin.enabled, status: !dshPlugin.enabled ? 'enabled' : 'installed' });
      })
      .finally(() => setPluginBusy(false));
  };

  return (
    <div
      className={`ctx-panel${embed ? ' is-embed' : ''} flex min-h-0 flex-1 flex-col overflow-y-auto ${
        embed ? 'px-3 py-2' : 'px-5 py-4'
      } apple-canvas`}
      data-testid={embed ? 'context-panel-embed' : 'context-panel'}
    >
      <ContextHeader
        embed={embed}
        locked={locked}
        taskId={taskId}
        traceOptions={traceOptions}
        data={data}
        stats={stats}
        windowSize={windowSize}
        showPrefs={showPrefs}
        onTogglePrefs={() => setShowPrefs((v) => !v)}
        trendGran={trendGran}
        onSelectGranularity={selectGranularity}
        trendMode={trendMode}
        onSelectMode={selectMode}
        dshPlugin={dshPlugin}
        pluginBusy={pluginBusy}
        onTogglePlugin={toggleDshPlugin}
        busy={busy}
        onRefresh={refresh}
        onSelectTask={selectTask}
      />

      {error ? (
        <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>
      ) : null}
      {data?.empty ? (
        <div className={`${cardCls} mb-3 text-[12px] text-[var(--console-sub)]`}>{data.message || '尚無 Context 資料'}</div>
      ) : null}

      <KpiGrid stats={stats} embed={embed} />

      <div className={`mb-4 grid gap-4 ${embed ? 'lg:grid-cols-2' : 'xl:grid-cols-2'}`}>
        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[var(--console-ink)]">Token / Timing</h3>
          <TokenTimingRings stats={stats} />
        </section>
        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[var(--console-ink)]">Current Context · 當前組成</h3>
          <CompositionBar
            composition={data?.composition || {}}
            maxWindow={windowSize}
            vsPrevious={data?.browser?.vs_previous}
          />
        </section>
      </div>

      <div className={`grid gap-4 ${embed ? 'lg:grid-cols-2' : 'xl:grid-cols-2'}`}>
        <TrendCard
          trend={displayTrend}
          step={step}
          onSelectStep={(s) => {
            setStep(s);
          }}
          mode={trendMode}
          onSelectMode={selectMode}
          granularity={trendGran}
          onSelectGranularity={selectGranularity}
          brief={brief}
          selectedTrend={selectedTrend}
        />

        <section className={cardCls}>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-[13px] font-semibold text-[var(--console-ink)]">Context Browser</h3>
            <span className="text-[10px] text-[var(--console-sub)]">
              {step == null ? 'Live' : `Step ${step}`}
            </span>
          </div>
          <BrowserPane
            browser={data?.browser || { step: null, categories: {} }}
            isLive={step == null || step === (data?.steps?.length ? data.steps.length - 1 : null)}
            onJumpLive={() => {
              const last = data?.steps?.length ? data.steps.length - 1 : null;
              setStep(last);
            }}
          />
        </section>

        <EventsCard
          events={events}
          kindFilter={kindFilter}
          onSelectKind={setKindFilter}
          embed={embed}
        />

        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[var(--console-ink)]">File Activity · 檔案活動</h3>
          <FileActivityPane rows={data?.file_activity || []} />
        </section>

        <section className={cardCls}>
          <h3 className="mb-2 text-[13px] font-semibold text-[var(--console-ink)]">Agent Network · 席位網</h3>
          <AgentNetworkPane nodes={data?.agent_network || []} />
        </section>
      </div>
    </div>
  );
}
