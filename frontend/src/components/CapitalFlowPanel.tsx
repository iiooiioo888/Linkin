/**
 * 量化策略資金流三視圖 — 瀑布／狀態機／時間軸。
 */
import { useEffect, useState } from 'react';
import { labQuantCapitalFlow, type QuantCapitalFlow } from '../api/client';
import MermaidBlock from './MermaidBlock';
import ErrorState from './ui/ErrorState';

type FlowTab = 'waterfall' | 'state' | 'timeline';

const TABS: { key: FlowTab; label: string; hint: string }[] = [
  { key: 'waterfall', label: '瀑布流向', hint: '資金當下分布 — 現金 vs 保證金 vs 準備金' },
  { key: 'state', label: '循環狀態機', hint: '一筆資金從進場到出場的完整旅程' },
  { key: 'timeline', label: '時間軸', hint: '現金／持倉／權益的數值變化紀錄' },
];

export default function CapitalFlowPanel({
  strategyId,
  symbol,
  strategyName,
  wired,
}: {
  strategyId: string | null;
  symbol: string;
  strategyName?: string;
  wired?: boolean;
}) {
  const [tab, setTab] = useState<FlowTab>('waterfall');
  const [data, setData] = useState<QuantCapitalFlow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!strategyId) {
      setData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void labQuantCapitalFlow(strategyId, { symbol })
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
      })
      .catch((err) => {
        if (cancelled) return;
        setData(null);
        setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [strategyId, symbol]);

  if (!strategyId) {
    return (
      <section className="apple-card sq-chart-card cf-panel">
        <div className="apple-card__head">
          <h2 className="apple-title">資金流</h2>
        </div>
        <p className="px-4 py-8 text-center text-[11px] text-[#636366]">選策略後顯示資金流視圖</p>
      </section>
    );
  }

  if (loading && !data) {
    return (
      <section className="apple-card sq-chart-card cf-panel">
        <div className="apple-card__head">
          <h2 className="apple-title">資金流</h2>
        </div>
        <p className="px-4 py-8 text-center text-[11px] text-[#8E8E93]">載入資金流…</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="apple-card sq-chart-card cf-panel">
        <div className="apple-card__head">
          <h2 className="apple-title">資金流</h2>
        </div>
        <ErrorState kind="partial" message={error} />
      </section>
    );
  }

  if (!data) return null;

  const activeHint = TABS.find((row) => row.key === tab)?.hint ?? '';
  const profile = data.profile;

  return (
    <section className="apple-card sq-chart-card cf-panel">
      <div className="apple-card__head">
        <div>
          <h2 className="apple-title">資金流</h2>
          <p className="mt-0.5 text-[10px] text-[#8E8E93]">
            {strategyName ?? data.name} · {data.symbol} · 初始 {data.initial_capital_fmt}
            {!wired ? ' · 示範路徑' : ''}
          </p>
        </div>
        <div className="cf-profile-chips">
          <span className="sq-tree-chip">現金 {profile.cash_buffer_pct}%</span>
          <span className="sq-tree-chip">保證金 {profile.margin_pct}%</span>
          <span className="sq-tree-chip">準備金 {profile.reserve_pct}%</span>
          {profile.stop_loss_pct ? (
            <span className="sq-tree-chip">停損 -{profile.stop_loss_pct}%</span>
          ) : null}
          {profile.trailing_stop_pct ? (
            <span className="sq-tree-chip">移動止損 -{profile.trailing_stop_pct}%</span>
          ) : null}
        </div>
      </div>

      <div className="cf-tabs">
        {TABS.map((row) => (
          <button
            key={row.key}
            type="button"
            className={`sq-tree-chip ${tab === row.key ? 'on' : ''}`}
            onClick={() => setTab(row.key)}
          >
            {row.label}
          </button>
        ))}
      </div>
      <p className="cf-tab-hint">{activeHint}</p>

      <div className="apple-card__body apple-card__body--static">
        {tab === 'waterfall' ? (
          <MermaidBlock chart={data.waterfall_mermaid} title="資金瀑布流向圖（桑基風格）" />
        ) : null}
        {tab === 'state' ? (
          <MermaidBlock chart={data.state_machine_mermaid} title="資金循環狀態機" />
        ) : null}
        {tab === 'timeline' ? (
          <div className="cf-timeline-wrap">
            <table className="cf-timeline">
              <thead>
                <tr>
                  <th>時間點</th>
                  <th>事件</th>
                  <th>現金餘額</th>
                  <th>持倉市值</th>
                  <th>保證金占用</th>
                  <th>總權益</th>
                  <th>資金流說明</th>
                </tr>
              </thead>
              <tbody>
                {data.timeline.map((row) => (
                  <tr key={`${row.time}-${row.event}`}>
                    <td>{row.time}</td>
                    <td>{row.event}</td>
                    <td>{row.cash}</td>
                    <td>{row.position}</td>
                    <td>{row.margin}</td>
                    <td className="cf-equity">{row.equity}</td>
                    <td>{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {data.backtest_summary ? (
        <div className="cf-backtest-bar">
          <span>
            回測報酬{' '}
            {data.backtest_summary.total_return != null
              ? `${(data.backtest_summary.total_return * 100).toFixed(1)}%`
              : '—'}
          </span>
          <span>
            最大回撤{' '}
            {data.backtest_summary.max_drawdown != null
              ? `${(data.backtest_summary.max_drawdown * 100).toFixed(1)}%`
              : '—'}
          </span>
          <span>交易 {data.backtest_summary.trades ?? '—'} 筆</span>
          <span>訊號 {data.backtest_summary.last_signal ?? '—'}</span>
        </div>
      ) : null}

      {data.disclaimer ? <p className="cf-disclaimer">{data.disclaimer}</p> : null}
    </section>
  );
}
