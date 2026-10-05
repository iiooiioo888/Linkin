/**
 * 情境規則建議 — 乾跑／套用閉環。
 */
import { useCallback, useState } from 'react';
import {
  fetchMinecraftSituationRules,
  runMinecraftSituationRules,
  type MinecraftSituationRuleRecommendation,
  type MinecraftSituationRulesRunResult,
} from '../../../api/linkin';
import { McPanel } from '../McChrome';
import { formatTs, statusLabel, useVisibilityPoll } from './shared';
import '../minecraft.css';

function actionTypeLabel(type: string): string {
  const map: Record<string, string> = {
    noop: '觀察',
    hint: '提示',
    player_assist: '玩家協助',
    region_focus: '區域焦點',
    quest_progress: '任務進度',
    npc_say: 'NPC 發言',
  };
  return map[type] || type;
}

function ApplyResultsBlock({ results }: { results: Array<Record<string, unknown>> }) {
  if (!results?.length) return <p className="mc-note">沒有可套用的安全動作，或僅記錄建議。</p>;
  return (
    <ul className="mc-rules__results">
      {results.map((row, idx) => (
        <li key={idx}>
          <span className="mc-rules__result-type">{String(row.type || '動作')}</span>
          <span className="mc-rules__result-status">{statusLabel(String(row.status || ''))}</span>
          {row.message ? <span className="mc-rules__result-msg">{String(row.message)}</span> : null}
          {row.error ? <span className="mc-error">{String(row.error)}</span> : null}
        </li>
      ))}
    </ul>
  );
}

function RecRow({ rec }: { rec: MinecraftSituationRuleRecommendation }) {
  return (
    <li className="mc-rules__rec">
      <div className="mc-rules__rec-top">
        <span className="mc-rules__rec-type">{actionTypeLabel(rec.action_type)}</span>
        {rec.auto_apply_safe ? <span className="mc-rules__safe">可安全套用</span> : null}
        {typeof rec.priority === 'number' ? (
          <span className="mc-rules__priority">優先 {rec.priority}</span>
        ) : null}
      </div>
      <p className="mc-rules__rec-msg">{rec.message || '（無說明）'}</p>
      {rec.rationale ? <p className="mc-rules__rec-rationale">{rec.rationale}</p> : null}
    </li>
  );
}

export default function SituationRulesPanel({ pollMs = 15000 }: { pollMs?: number }) {
  const [recommendations, setRecommendations] = useState<MinecraftSituationRuleRecommendation[]>([]);
  const [generatedAt, setGeneratedAt] = useState<number | null>(null);
  const [recentRunTs, setRecentRunTs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<MinecraftSituationRulesRunResult | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const bundle = await fetchMinecraftSituationRules(8);
      const snap = bundle?.snapshot;
      setRecommendations(Array.isArray(snap?.rule_recommendations) ? snap.rule_recommendations : []);
      setGeneratedAt(snap?.generated_at ?? null);
      const runs = bundle?.recent_runs;
      setRecentRunTs(runs?.[0]?.ts ?? null);
    } catch (err) {
      setRecommendations([]);
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useVisibilityPoll(load, pollMs);

  const handleRun = useCallback(
    async (dryRun: boolean) => {
      if (!dryRun) {
        const ok = window.confirm(
          '確定要套用情境規則？僅會自動套用標記為「可安全套用」的動作；其餘仍僅記錄建議。',
        );
        if (!ok) return;
      }
      setRunning(true);
      setError(null);
      setLastResult(null);
      try {
        const result = await runMinecraftSituationRules(dryRun);
        setLastResult(result);
        if (!result?.ok) {
          setError(result?.error || '規則執行失敗');
        }
        await load();
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setRunning(false);
      }
    },
    [load],
  );

  const recs = recommendations ?? [];

  return (
    <McPanel
      title="規則建議"
      hint="依四維情境自動產生"
      action={
        <div className="mc-rules__actions">
          <button type="button" className="mc-btn" disabled={running || loading} onClick={() => void handleRun(true)}>
            {running ? '執行中…' : '乾跑'}
          </button>
          <button
            type="button"
            className="mc-btn is-primary"
            disabled={running || loading}
            onClick={() => void handleRun(false)}
          >
            套用
          </button>
        </div>
      }
    >
      <div className="mc-rules__toolbar">
        <span className="mc-panel__hint">
          {loading ? '讀取中' : generatedAt ? `快照 ${formatTs(generatedAt)}` : '—'}
          {recentRunTs ? ` · 最近執行 ${formatTs(recentRunTs)}` : ''}
        </span>
        <button type="button" className="mc-btn" onClick={() => void load()} disabled={loading}>
          重新整理
        </button>
      </div>

      {error ? <p className="mc-error">{error}</p> : null}

      {!loading && !recs.length && !error ? (
        <p className="mc-empty">目前沒有規則建議；四維情境更新後會出現可執行項目。</p>
      ) : null}

      {recs.length ? (
        <ul className="mc-rules__list">
          {recs.map((rec) => (
            <RecRow key={rec.id || rec.message} rec={rec} />
          ))}
        </ul>
      ) : null}

      {lastResult ? (
        <div className="mc-rules__outcome" role="status">
          <p className="mc-rules__outcome-title">
            {lastResult.ok ? '執行完成' : '執行失敗'}
            {lastResult.run_id ? ` · ${lastResult.run_id}` : ''}
            {lastResult.auto_applied ? ' · 已套用安全動作' : ''}
          </p>
          {lastResult.error ? <p className="mc-error">{lastResult.error}</p> : null}
          {lastResult.recommendations?.length ? (
            <details className="mc-rules__diff">
              <summary>建議清單（{lastResult.recommendations.length}）</summary>
              <ul className="mc-rules__list mc-rules__list--compact">
                {lastResult.recommendations.map((rec) => (
                  <RecRow key={`run-${rec.id}`} rec={rec} />
                ))}
              </ul>
            </details>
          ) : null}
          <ApplyResultsBlock results={lastResult.apply_results ?? []} />
        </div>
      ) : null}
    </McPanel>
  );
}
