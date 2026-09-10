/**
 * UserFeedbackPanel — 用戶反饋分析（信號分布 + 評論詞雲）。
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchOptimizationMonitor } from '../api/client';
import type { OptimizationMonitorData } from '../types';
import {
  ConsoleCard,
  ConsoleCardBody,
  ConsoleCardHeader,
  KpiCard,
  KpiGrid,
  PanelAlert,
  PanelSection,
  PanelShell,
  SectionHeader,
  consoleLayout,
} from './ui/ConsoleLayout';

const SIGNAL_LABELS: Record<string, string> = {
  thumbs_up: '👍 讚',
  thumbs_down: '👎 踩',
  copy: '📋 複製',
  edit: '✏️ 編輯',
};

function WordCloud({
  words,
}: {
  words: Array<{ word: string; count: number; weight: number }>;
}) {
  if (!words.length) {
    return <p className="text-xs text-[#62666d]">尚無評論詞彙，用戶留下 comment 後將生成詞雲。</p>;
  }
  return (
    <div className="flex flex-wrap items-center justify-center gap-2 py-4">
      {words.map((item) => {
        const size = 11 + Math.round(item.weight * 14);
        const opacity = 0.55 + item.weight * 0.45;
        return (
          <span
            key={item.word}
            className="rounded-md px-1.5 py-0.5 font-medium text-[#64D2FF]"
            style={{ fontSize: `${size}px`, opacity }}
            title={`${item.count} 次`}
          >
            {item.word}
          </span>
        );
      })}
    </div>
  );
}

export default function UserFeedbackPanel() {
  const [data, setData] = useState<OptimizationMonitorData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchOptimizationMonitor();
      setData(next);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  const fb = data?.feedback_analysis;
  const satisfaction = Math.round((fb?.satisfaction_rate ?? 0) * 100);
  const signals = fb?.signal_counts ?? {};
  const signalTotal = Object.values(signals).reduce((a, b) => a + b, 0) || 1;

  return (
    <PanelShell>
      <PanelSection>
        <SectionHeader
          title="用戶反饋分析"
          description="顯式反饋（讚/踩）與隱式信號（複製/編輯）· 驅動動態閾值自適應"
          actions={
            <button type="button" onClick={() => void refresh()} className={consoleLayout.refreshBtn}>
              {loading ? '同步中' : '重新整理'}
            </button>
          }
        />

        {error ? <PanelAlert>{error}</PanelAlert> : null}

        <KpiGrid>
          {[
            { label: '滿意度', value: `${satisfaction}%` },
            { label: '總樣本', value: String(fb?.total ?? 0) },
            { label: '平均評分', value: fb?.avg_score != null ? String(fb.avg_score) : '—' },
            {
              label: '評分分布',
              value: `${fb?.score_buckets?.high ?? 0}/${fb?.score_buckets?.mid ?? 0}/${fb?.score_buckets?.low ?? 0}`,
              hint: '高/中/低',
            },
          ].map((kpi) => (
            <KpiCard key={kpi.label} label={kpi.label} value={kpi.value} hint={kpi.hint} />
          ))}
        </KpiGrid>

        <div className={consoleLayout.cardGrid}>
          <ConsoleCard>
            <ConsoleCardHeader>信號分布</ConsoleCardHeader>
            <ConsoleCardBody dense className="space-y-2">
            {Object.entries(signals).map(([key, count]) => (
              <div key={key}>
                <div className="mb-1 flex justify-between text-xs">
                  <span>{SIGNAL_LABELS[key] ?? key}</span>
                  <span className="tabular-nums text-[#8a8f98]">
                    {count} ({Math.round((count / signalTotal) * 100)}%)
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-[#141516]">
                  <div
                    className="h-full rounded-full bg-[#007AFF]"
                    style={{ width: `${(count / signalTotal) * 100}%` }}
                  />
                </div>
              </div>
            ))}
            </ConsoleCardBody>
          </ConsoleCard>

          <ConsoleCard>
            <ConsoleCardHeader>評論詞雲</ConsoleCardHeader>
            <WordCloud words={fb?.word_cloud ?? []} />
          </ConsoleCard>
        </div>

        <ConsoleCard>
          <ConsoleCardHeader>最近反饋</ConsoleCardHeader>
          <div className="divide-y divide-white/[0.06]">
          {(fb?.recent ?? []).length === 0 ? (
            <p className="p-3 text-xs text-[#62666d]">尚無反饋記錄</p>
          ) : (
            fb?.recent
              .slice()
              .reverse()
              .map((rec, idx) => (
                <div key={`${rec.session_id}-${idx}`} className="flex flex-wrap gap-2 px-3 py-2 text-xs">
                  <span className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[#64D2FF]">
                    {SIGNAL_LABELS[rec.signal ?? ''] ?? rec.signal}
                  </span>
                  {rec.score != null && (
                    <span className="font-mono text-[#8a8f98]">評分 {rec.score}</span>
                  )}
                  {rec.comment && <span className="text-[#d0d6e0]">{rec.comment}</span>}
                </div>
              ))
          )}
          </div>
        </ConsoleCard>
      </PanelSection>
    </PanelShell>
  );
}
