/**
 * GrillUserCard — L4 需求審計官：五維鎖定對話卡。
 */
import { useState } from 'react';
import type { AuditorScores, GrillUserState } from '../types';

interface GrillUserCardProps {
  grill: GrillUserState;
  disabled?: boolean;
  onAnswer: (answer: string, forceLock?: boolean) => void;
}

const DIM_ROWS: Array<{ key: keyof AuditorScores; label: string }> = [
  { key: 'specificity', label: '目標具體性' },
  { key: 'boundary', label: '邊界清晰度' },
  { key: 'constraints', label: '約束量化度' },
  { key: 'risk', label: '風險感知度' },
  { key: 'success', label: '成功定義' },
];

function dimValue(scores: AuditorScores | undefined, key: keyof AuditorScores): number {
  const raw = scores?.[key];
  return typeof raw === 'number' ? raw : 0;
}

export default function GrillUserCard({ grill, disabled, onAnswer }: GrillUserCardProps) {
  const [text, setText] = useState('');
  const pct = Math.round((grill.confidence ?? 0) * 100);
  const locked = Boolean(grill.locked);
  const terminated = Boolean(grill.terminated);
  const closed = locked || terminated;

  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onAnswer(trimmed, false);
    setText('');
  };

  return (
    <div className={`raho-grill-card${terminated ? ' is-failed' : ''}${locked ? ' is-locked' : ''}`}>
      <div className="raho-grill-head">
        <span className="raho-grill-kicker">{grill.role_label || 'L4 需求審計官'}</span>
        <span className={pct > 90 ? 'text-[#30D158]' : terminated ? 'text-[#FF453A]' : 'text-[#FF9F0A]'}>
          {terminated ? '審計失敗' : locked ? '已核發門票' : `綜合 ${pct}%`}
        </span>
      </div>
      <p className="raho-grill-lead">
        {terminated
          ? '終止協議已觸發，禁止進入 Planner。'
          : locked
            ? '五維達標。戰術指令已核發，即將交給 Dynamic Planner。'
            : `${grill.phase_label || 'Phase 1 基礎錨定'} · 模糊回答（大概／盡量／好一點）視為無效。`}
      </p>
      <div className="raho-grill-dims">
        {DIM_ROWS.map((row) => {
          const val = dimValue(grill.scores, row.key);
          const ok = val > 90;
          return (
            <div key={row.key} className="raho-dim">
              <div className="raho-dim-meta">
                <span>{row.label}</span>
                <span className={ok ? 'ok' : ''}>{Math.round(val)}</span>
              </div>
              <div className="raho-grill-meter">
                <div
                  className={`raho-grill-meter-fill${ok ? ' is-ok' : ''}`}
                  style={{ width: `${Math.min(100, val)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="raho-grill-log">
        {(grill.history ?? []).map((turn, i) => (
          <div key={`${turn.role}-${i}`} className={turn.role === 'assistant' ? 'raho-q' : 'raho-a'}>
            <span>{turn.role === 'assistant' ? '審計官' : '你'}</span>
            <p>{turn.content}</p>
            {turn.why ? <em>{turn.why}</em> : null}
          </div>
        ))}
      </div>
      {terminated && grill.termination_report ? (
        <pre className="raho-fail-report">{grill.termination_report}</pre>
      ) : null}
      {locked && grill.ticket ? (
        <pre className="raho-ticket">{JSON.stringify(grill.ticket, null, 2)}</pre>
      ) : null}
      {!closed && (
        <div className="raho-grill-composer">
          <textarea
            value={text}
            disabled={disabled}
            rows={3}
            placeholder="請給數字、時程、邊界與備案。禁止大概／盡量／你看著辦。"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <div className="raho-grill-actions">
            <button type="button" disabled={disabled || !text.trim()} className="raho-btn" onClick={submit}>
              回答並接受審查
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
