/**
 * L0 環境與記憶核心：記憶瀏覽器／知識圖譜／態勢雷達。
 * 與質詢樹、角色名冊共用同一套指揮／審查／核心身分。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchL0Kernel } from '../api/client';
import type { L0Snapshot } from '../types';
import MemoryPanel from './MemoryPanel';
import LcSpiderChart from './charts/LcSpiderChart';
import { jumpToGrillTree, RAHO_LAYERS } from '../lib/rahoUi';

type L0Tab = 'memory' | 'knowledge' | 'radar' | 'vectors';

export default function L0Panel({
  snapshot,
  query = '',
  nodeId = '',
  embed = false,
  initialTab = 'memory',
}: {
  snapshot?: L0Snapshot | null;
  query?: string;
  nodeId?: string;
  embed?: boolean;
  initialTab?: L0Tab;
}) {
  const [tab, setTab] = useState<L0Tab>(initialTab);
  const [data, setData] = useState<L0Snapshot>(snapshot ?? {});
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const next = await fetchL0Kernel(query, nodeId);
      setData(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [query, nodeId]);

  useEffect(() => {
    setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    if (snapshot && !query && !nodeId) {
      setData(snapshot);
      return;
    }
    void reload();
    const t = setInterval(() => void reload(), 6000);
    return () => clearInterval(t);
  }, [reload, snapshot, query, nodeId]);

  const radar = data.radar ?? {};
  const metrics = radar.metrics ?? {};
  const pressure = Math.round((radar.pressure ?? 0) * 100);
  const traces = useMemo(() => {
    const rows = data.traces ?? [];
    if (!nodeId) return rows;
    const focused = rows.filter((t) => t.node_id === nodeId);
    return focused.length ? focused : rows;
  }, [data.traces, nodeId]);
  const knowledge = data.knowledge ?? [];
  const spider = useMemo(
    () => [
      { axis: 'Token', value: Math.round((metrics.token_usage_ratio ?? 0) * 100) },
      { axis: '延遲', value: Math.min(100, Math.round((metrics.avg_latency_ms ?? 0) / 40)) },
      { axis: '質詢失敗', value: Math.round((metrics.grill_fail_rate ?? 0) * 100) },
      { axis: '待決', value: Math.min(100, Math.round((metrics.pending_decisions ?? 0) * 20)) },
      { axis: '催促', value: metrics.user_urgency === 'high' ? 90 : 20 },
      {
        axis: '市場',
        value:
          metrics.external_market_sentiment === 'bearish' || metrics.external_market_sentiment === 'risk_off'
            ? 80
            : 30,
      },
    ],
    [metrics],
  );

  return (
    <div className={`l0-panel${embed ? ' is-embed' : ''}`}>
      <div className="l0-head">
        <div>
          <h2 className="l0-title">{RAHO_LAYERS[0]?.full ?? 'L0 環境與記憶核心'}</h2>
          <p className="l0-sub">
            三核驅動：記憶整理、知識圖譜、態勢偏置。不執行任務，只滲透 L1–L5。
            {nodeId ? ` · 節點 ${nodeId}` : ''}
          </p>
        </div>
        <div className="l0-head-acts">
          <span className={`l0-pressure${radar.energy_save ? ' is-hot' : ''}`}>壓力 {pressure}%</span>
          <button type="button" className="rd-btn text-[11px] text-[#0A84FF]" onClick={() => void reload()}>
            重新整理
          </button>
        </div>
      </div>
      {error ? <p className="mb-3 text-[12px] text-[#FF453A]">{error}</p> : null}

      <div className="l0-tabs" role="tablist">
        {(
          [
            ['memory', '記憶瀏覽器'],
            ['knowledge', '知識圖譜'],
            ['radar', '態勢雷達'],
            ...(!embed ? ([['vectors', '向量庫']] as const) : []),
          ] as Array<[L0Tab, string]>
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`l0-tab${tab === key ? ' on' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'memory' && (
        <div className="l0-body">
          {traces.length === 0 ? (
            <p className="py-10 text-center text-[12px] text-[#636366]">尚無記憶軌跡。質詢與簽核發生後會在此回放。</p>
          ) : (
            <ol className="l0-list">
              {traces.map((trace) => (
                <li key={`${trace.task_id}-${trace.node_id}-${trace.summary}`} className="l0-card">
                  <div className="l0-card-k">
                    {trace.horizon === 'stm' ? '短期' : trace.horizon === 'ltm' ? '長期' : '中期'} · {trace.layer}
                    {trace.node_id ? ` · ${trace.node_id}` : ''}
                  </div>
                  <p className="l0-card-t">{trace.summary}</p>
                  {trace.failure_reason ? <p className="l0-card-f">教訓：{trace.failure_reason}</p> : null}
                  {(trace.decisions?.length ?? 0) > 0 ? (
                    <p className="l0-card-d">{trace.decisions!.join('／')}</p>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
          <button type="button" className="l0-link" onClick={jumpToGrillTree}>
            對照質詢樹
          </button>
        </div>
      )}

      {tab === 'knowledge' && (
        <div className="l0-body">
          {knowledge.length === 0 ? (
            <p className="py-10 text-center text-[12px] text-[#636366]">尚無引用實體。審計或拆解時會自動掛上知識卡。</p>
          ) : (
            <ol className="l0-graph">
              {knowledge.map((item) => (
                <li key={item.id} className="l0-card">
                  <div className="l0-card-k">{item.id}</div>
                  <p className="l0-card-t">{item.content}</p>
                  {(item.relations?.length ?? 0) > 0 ? (
                    <div className="l0-chips">
                      {item.relations!.map((rel) => (
                        <span key={rel} className="l0-chip">
                          {rel}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}

      {tab === 'radar' && (
        <div className="l0-body">
          <p className="l0-bias">{radar.bias_instructions || '環境壓力正常。'}</p>
          <div className="l0-thermo" aria-label="環境壓力">
            <i style={{ height: `${pressure}%` }} />
            <span>{pressure}%</span>
          </div>
          <LcSpiderChart points={spider} height={240} max={100} />
          <div className="l0-metrics">
            <RadarCell label="Token" value={`${Math.round((metrics.token_usage_ratio ?? 0) * 100)}%`} />
            <RadarCell label="延遲" value={`${Math.round(metrics.avg_latency_ms ?? 0)} ms`} />
            <RadarCell label="質詢失敗" value={`${Math.round((metrics.grill_fail_rate ?? 0) * 100)}%`} />
            <RadarCell label="待決" value={String(metrics.pending_decisions ?? 0)} />
            <RadarCell label="催促" value={String(metrics.user_urgency ?? 'normal')} />
            <RadarCell label="市場" value={String(metrics.external_market_sentiment ?? 'neutral')} />
          </div>
          {radar.energy_save ? (
            <p className="l0-warn">節能模式：L1 僅能對邊界項降級通過；L3 應降低 Max Iterations。</p>
          ) : null}
        </div>
      )}

      {tab === 'vectors' && !embed ? (
        <div className="l0-vectors">
          <MemoryPanel />
        </div>
      ) : null}
    </div>
  );
}

function RadarCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="l0-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
