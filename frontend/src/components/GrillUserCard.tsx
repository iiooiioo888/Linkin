/**
 * GrillUserCard — L4 需求審計官：四階段烤問 + 五維鎖定對話卡。
 * 主路徑為點選方案（與 RahoDecisionBar 一致），非自由輸入。
 */
import { useState } from 'react';
import type { AuditorScores, GrillChoice, GrillUserState } from '../types';
import { L0BiasHint } from './L0BiasHint';

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

const PHASES = [
  { id: 1, label: '基礎錨定' },
  { id: 2, label: '量化絞殺' },
  { id: 3, label: '壓力測試' },
  { id: 4, label: '語義鎖定' },
];

function plannerCaption(planner: Record<string, unknown> | null | undefined): string {
  if (!planner) return '';
  const status = String(planner.status || '');
  if (status === 'PLANNER_TRIGGERED') return '戰術指令已交給 Dynamic Planner，戰役 DAG 已產出。';
  if (status === 'REJECTED') return `規劃器拒絕：${String(planner.reason || '門票未達門檻')}`;
  if (status === 'PLANNER_DEFERRED') return '門票已核發，規劃器稍後補跑。';
  return '';
}

function dimValue(scores: AuditorScores | undefined, key: keyof AuditorScores): number {
  const raw = scores?.[key];
  return typeof raw === 'number' ? raw : 0;
}

function choiceKey(c: GrillChoice, idx: number): string {
  return String(c.key || c.label || idx);
}

export default function GrillUserCard({ grill, disabled, onAnswer }: GrillUserCardProps) {
  const [customOpen, setCustomOpen] = useState(false);
  const [customText, setCustomText] = useState('');
  const pct = Math.round((grill.confidence ?? 0) * 100);
  const locked = Boolean(grill.locked);
  const terminated = Boolean(grill.terminated);
  const closed = locked || terminated;
  const phase = Number(grill.phase || 1);
  const userRounds = grill.user_rounds ?? (grill.history ?? []).filter((t) => t.role === 'user').length;
  const maxTurns = grill.max_turns ?? 10;
  const phaseRounds = grill.phase_rounds ?? 0;
  const choices = grill.question?.choices ?? [];

  const pickChoice = (choice: GrillChoice) => {
    const label = String(choice.label || '').trim();
    if (!label || disabled) return;
    onAnswer(label, false);
    setCustomOpen(false);
    setCustomText('');
  };

  const submitCustom = () => {
    const trimmed = customText.trim();
    if (!trimmed || disabled) return;
    onAnswer(trimmed, false);
    setCustomText('');
    setCustomOpen(false);
  };

  return (
    <div className={`raho-grill-card${terminated ? ' is-failed' : ''}${locked ? ' is-locked' : ''}`}>
      <div className="raho-grill-head">
        <span className="raho-grill-kicker">
          {grill.role_label || 'L4 需求審計官'}
          <em className="raho-grill-gate">強制前置閘門</em>
        </span>
        <span className={pct > 90 ? 'text-[#30D158]' : terminated ? 'text-[#FF453A]' : 'text-[#FF9F0A]'}>
          {terminated ? '審計失敗' : locked ? '已核發門票' : `綜合 ${pct}%`}
        </span>
      </div>
      <div className="raho-phase-stepper" aria-label="審計階段">
        {PHASES.map((row) => (
          <div
            key={row.id}
            className={`raho-phase-step${row.id === phase && !locked ? ' is-active' : ''}${row.id < phase || locked ? ' is-done' : ''}`}
          >
            <i>{row.id}</i>
            <span>{row.label}</span>
          </div>
        ))}
      </div>
      <p className="raho-grill-meta">
        {closed
          ? terminated
            ? '終止協議已觸發'
            : '五維達標，門票已核發'
          : `第 ${userRounds}/${maxTurns} 輪 · 本階段 ${phaseRounds}/3`}
      </p>
      <p className="raho-grill-lead">
        {terminated
          ? '終止協議已觸發，禁止進入 Planner。'
          : locked
            ? plannerCaption(grill.planner) ||
              '五維達標。戰術指令已核發，即將交給 Dynamic Planner 與 L3 戰術指揮官。'
            : `${grill.phase_label || 'Phase 1 基礎錨定'} · 請點選最符合的一項；模糊選項仍會被視為無效。`}
      </p>
      <L0BiasHint snapshot={grill.l0} compact />
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
        <div className="raho-ticket-wrap">
          <p className="raho-ticket-label">戰術指令文件 · APPROVED_FOR_PLANNING</p>
          <pre className="raho-ticket">{JSON.stringify(grill.ticket, null, 2)}</pre>
        </div>
      ) : null}
      {!closed && (
        <div className="raho-grill-composer">
          {grill.question?.question ? (
            <p className="raho-grill-current-q">{grill.question.question}</p>
          ) : null}
          {grill.question?.why ? <p className="raho-grill-current-why">{grill.question.why}</p> : null}
          {choices.length > 0 ? (
            <div className="raho-grill-choices" role="listbox" aria-label="審計回答選項">
              {choices.map((c, idx) => (
                <button
                  key={choiceKey(c, idx)}
                  type="button"
                  disabled={disabled}
                  className={`raho-decision-choice raho-grill-choice${c.key === 'vague' ? ' is-vague' : ''}`}
                  onClick={() => pickChoice(c)}
                >
                  {c.label || c.key}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-[12px] text-[#8E8E93]">載入選項中…</p>
          )}
          <div className="raho-grill-actions">
            <button
              type="button"
              className="raho-btn raho-btn--ghost"
              disabled={disabled}
              onClick={() => setCustomOpen((v) => !v)}
            >
              {customOpen ? '收起自訂' : '其他（簡短補充）'}
            </button>
          </div>
          {customOpen ? (
            <div className="raho-grill-custom">
              <textarea
                value={customText}
                disabled={disabled}
                rows={2}
                placeholder="僅在選項都不適用時補充；仍須含數字、時程或邊界。"
                onChange={(e) => setCustomText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    submitCustom();
                  }
                }}
              />
              <button
                type="button"
                disabled={disabled || !customText.trim()}
                className="raho-btn"
                onClick={submitCustom}
              >
                送出補充
              </button>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
