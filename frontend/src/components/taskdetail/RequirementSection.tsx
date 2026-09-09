/**
 * 02 需求分析 — L4 需求審計官的門票（五維評分＋硬約束＋風險登記＋逐輪留痕）。
 *
 * 這張門票過去只存在於後端 options.auditor_ticket，問完就在 UI 上蒸發；
 * 本區塊把它完整還原。五維一律用純 CSS 橫向條形（不引入圖表依賴）。
 */
import type { ReactNode } from 'react';
import type { AuditorTicket, TaskProgress } from '../../types';
import { DIMENSION_GATE, DIMENSION_META, ticketStatusLabel } from './labels';
import {
  AnyValue,
  CARD_CLS,
  Card,
  ChipList,
  CopyButton,
  EmptyState,
  Field,
  FieldGrid,
  JsonBlock,
  LongText,
  ScoreBar,
  SectionHead,
  SubHead,
} from './parts';
import { listOf, num, restKeys, textField, ticketOf } from './narrow';

const USED_TICKET_KEYS = [
  'status',
  'confidence_score',
  'clarified_goal',
  'hard_constraints',
  'risk_register',
  'audit_trail',
  'dimension_scores',
];

function ConstraintCard({
  title,
  note,
  tone,
  children,
}: {
  title: string;
  note?: string;
  tone: string;
  children: ReactNode;
}) {
  return (
    <Card tone={tone}>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-[10.5px] font-semibold tracking-[0.03em]" style={{ color: tone }}>
          {title}
        </span>
        {note ? <span className="text-[9px] text-[var(--apple-tertiary)]">{note}</span> : null}
      </div>
      <div className="min-w-0 text-[11.5px] leading-relaxed text-[var(--apple-label)]">{children}</div>
    </Card>
  );
}

function TrailBlock({ trail }: { trail: string[] }) {
  return (
    <details className={CARD_CLS}>
      <summary className="flex cursor-pointer list-none items-center gap-2 text-[11px] text-[var(--apple-secondary)] hover:text-[var(--apple-label)]">
        <span aria-hidden>▸</span>
        <span>展開 {trail.length} 條追問與回答留痕</span>
      </summary>
      <ol className="mt-2 space-y-1.5 border-t border-[var(--apple-hairline)] pt-2">
        {trail.map((row, i) => (
          <li key={i} className="flex gap-2 text-[11.5px] leading-relaxed">
            <span className="apple-data shrink-0 text-[var(--apple-tertiary)]">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap break-words text-[var(--apple-secondary)]">
              {row}
            </span>
          </li>
        ))}
      </ol>
    </details>
  );
}

function TicketBody({ ticket }: { ticket: AuditorTicket }) {
  const dims = ticket.dimension_scores ?? {};
  const goal = ticket.clarified_goal ?? {};
  const hard = ticket.hard_constraints ?? {};
  const risk = ticket.risk_register ?? {};
  const confidence = num(ticket.confidence_score);
  const trail = listOf(ticket.audit_trail);
  const risks = listOf(risk.identified_risks);
  const hasDims = DIMENSION_META.some((row) => num(dims[row.key]) != null);
  const rest = restKeys(ticket as unknown as Record<string, unknown>, USED_TICKET_KEYS);

  return (
    <>
      <SubHead>審計狀態</SubHead>
      <Card tone={confidence != null && confidence > DIMENSION_GATE ? 'var(--apple-green)' : 'var(--apple-orange)'}>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
          <span className="text-[12px] text-[var(--apple-label)]">
            門票狀態：
            <span className="apple-data ml-1 text-[var(--apple-blue-soft)]">
              {ticketStatusLabel(ticket.status)}
            </span>
          </span>
          <span className="apple-data text-[11px] text-[var(--apple-secondary)]">
            置信度 {confidence != null ? Math.round(confidence * 10) / 10 : '—'} ／ 100
          </span>
          <span className="text-[10.5px] text-[var(--apple-tertiary)]">
            放行條件：五維皆 &gt; {DIMENSION_GATE} 且完成語義鎖定
          </span>
        </div>
        <div className="mt-2">
          <ScoreBar label="綜合置信度（confidence_score）" value={confidence} threshold={DIMENSION_GATE} />
        </div>
      </Card>

      <SubHead count={DIMENSION_META.length}>五維評分（dimension_scores）</SubHead>
      <Card>
        {hasDims ? (
          <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
            {DIMENSION_META.map((row) => {
              const v = num(dims[row.key]);
              const ok = v != null && v > DIMENSION_GATE;
              return (
                <div key={row.key} className="min-w-0">
                  <ScoreBar
                    label={
                      <span>
                        {row.label}
                        <span className="apple-data ml-1 text-[9px] text-[var(--apple-tertiary)]">
                          {row.key}
                        </span>
                      </span>
                    }
                    value={v}
                    threshold={DIMENSION_GATE}
                    tone={ok ? 'var(--apple-green)' : v == null ? 'var(--apple-tertiary)' : 'var(--apple-red)'}
                  />
                  <p className="mt-0.5 text-[9.5px] leading-snug text-[var(--apple-tertiary)]">{row.note}</p>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-[11px] text-[var(--apple-tertiary)]">
            門票未附五維分數 — 可能為審計器改版前的舊任務，或用戶以裁決直接強制放行。
          </p>
        )}
      </Card>

      <SubHead>澄清後的目標（clarified_goal）</SubHead>
      <FieldGrid>
        <Field label="目標受眾（target_audience）" value={goal.target_audience} />
        <Field label="核心動作（core_action）" value={goal.core_action} />
        <Field
          label="量化成功標準（quantified_success）"
          wide
          value={
            goal.quantified_success ? (
              <span className="whitespace-pre-wrap break-words">{goal.quantified_success}</span>
            ) : null
          }
        />
      </FieldGrid>

      <SubHead>硬約束與風險登記</SubHead>
      <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2">
        <ConstraintCard title="必須使用" note="must_use_tech・既有資源不得替換" tone="var(--apple-blue)">
          <ChipList items={listOf(hard.must_use_tech)} tone="var(--apple-blue)" empty="未指定既有技術棧" />
        </ConstraintCard>
        <ConstraintCard title="絕不做" note="absolute_exclusions・驗收否決項" tone="var(--apple-red)">
          <ChipList items={listOf(hard.absolute_exclusions)} tone="var(--apple-red)" empty="未登記絕對不做項" />
        </ConstraintCard>
        <ConstraintCard title="截止" note="hard_constraints.deadline" tone="var(--apple-orange)">
          {textField(hard.deadline) || <span className="text-[var(--apple-tertiary)]">未設定</span>}
        </ConstraintCard>
        <ConstraintCard title="預算" note="hard_constraints.budget_range" tone="var(--apple-orange)">
          {textField(hard.budget_range) || <span className="text-[var(--apple-tertiary)]">未設定</span>}
        </ConstraintCard>
        <ConstraintCard title="風險備案" note={`risk_register・已預判 ${risks.length} 項`} tone="#bf5af2">
          {risks.length ? (
            <ol className="space-y-1">
              {risks.map((r, i) => (
                <li key={i} className="flex gap-1.5">
                  <span className="apple-data shrink-0 text-[var(--apple-tertiary)]">R{i + 1}</span>
                  <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{r}</span>
                </li>
              ))}
            </ol>
          ) : (
            <span className="text-[var(--apple-tertiary)]">未登記風險 — 審計器視為高不確定</span>
          )}
        </ConstraintCard>
        <ConstraintCard title="取捨順序" note="risk_register.user_priority・超支時先犧牲什麼" tone="var(--apple-green)">
          {textField(risk.user_priority) ? (
            <span className="whitespace-pre-wrap break-words">{textField(risk.user_priority)}</span>
          ) : (
            <span className="text-[var(--apple-tertiary)]">用戶未給取捨順序</span>
          )}
        </ConstraintCard>
      </div>

      <SubHead count={trail.length}>逐輪留痕（audit_trail）</SubHead>
      {trail.length ? (
        <TrailBlock trail={trail} />
      ) : (
        <EmptyState title="門票未附逐輪留痕" note="audit_trail 為空：直通任務或舊版審計器未留痕。" />
      )}

      {Object.keys(rest).length ? (
        <>
          <SubHead count={Object.keys(rest).length}>門票其他欄位</SubHead>
          <FieldGrid>
            {Object.entries(rest).map(([k, v]) => (
              <Field
                key={k}
                label={k}
                value={<AnyValue value={v} />}
                wide={typeof v === 'string' && v.length > 60}
              />
            ))}
          </FieldGrid>
          <JsonBlock value={rest} label="門票剩餘欄位原始 JSON" />
        </>
      ) : null}
    </>
  );
}

export default function RequirementSection({ task }: { task: TaskProgress }) {
  const ticket = ticketOf(task);
  const brief = (task.options?.locked_brief || '').trim();
  const semantic = (task.options?.semantic_brief || '').trim();
  const briefText = brief || semantic;

  return (
    <>
      <SectionHead
        index={2}
        title="需求分析"
        hint="L4 需求審計官核發的門票 — 追問結果的最終憑證"
        right={
          ticket ? (
            <span className="apple-data text-[var(--apple-green)]">
              ✓ 已附門票（{ticketStatusLabel(ticket.status)}）
            </span>
          ) : (
            <span className="text-[var(--apple-tertiary)]">無門票</span>
          )
        }
      />

      {ticket ? (
        <TicketBody ticket={ticket} />
      ) : (
        <EmptyState
          title="此任務未經需求審計（直通）"
          note="options.auditor_ticket 為空：任務被判定為簡單需求，L4 需求審計官未介入，因此沒有五維評分、硬約束、風險登記與逐輪留痕。若想看見門票，請在對話中完成審計問答後再送出，或將執行策略改為 company。"
        />
      )}

      <SubHead>戰術指令全文（locked_brief）</SubHead>
      {briefText ? (
        <Card>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <span className="text-[10px] text-[var(--apple-tertiary)]">
              {brief ? 'options.locked_brief' : 'options.semantic_brief（未附 locked_brief，改以語義簡報）'}
              ・上游審計官交給 Planner 的唯一依據
            </span>
            <CopyButton text={briefText} label="複製全文" />
          </div>
          {brief && semantic && semantic !== brief ? (
            <LongText text={semantic} label="語義鎖定簡報（semantic_brief）" />
          ) : null}
          <LongText text={briefText} label="戰術指令全文" defaultOpen />
        </Card>
      ) : (
        <EmptyState
          title="未鎖定戰術指令"
          note="locked_brief 與 semantic_brief 皆空：Planner 直接使用原始 query，未經語義鎖定。"
        />
      )}
    </>
  );
}
