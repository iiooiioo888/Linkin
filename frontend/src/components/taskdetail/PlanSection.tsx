/**
 * 03 作戰計劃 — Manager 分解計劃、L3 戰役地圖與原子作戰計劃（battle_plan）。
 */
import type { AtomicRoleInstance, BattleDagNode, TaskProgress } from '../../types';
import { roleLabel } from '../TaskPanel';
import {
  Card,
  Chip,
  ChipList,
  EmptyState,
  Field,
  FieldGrid,
  JsonBlock,
  LongText,
  SectionHead,
  SubHead,
} from './parts';
import {
  battlePlanOf,
  campaignOf,
  commanderOf,
  listOf,
  planOf,
  textField,
} from './narrow';

const LI_CLS =
  'rounded-[7px] border border-[var(--apple-hairline)] bg-[var(--apple-surface)] p-2.5';

function formatRef(ref?: string | string[]): string {
  if (!ref) return '';
  return Array.isArray(ref) ? ref.join(' → ') : String(ref);
}

function DagNodeRow({ node }: { node: BattleDagNode }) {
  const parallel = node.parallel_ok || !node.depends_on?.length;
  return (
    <li className={`${LI_CLS} min-w-0`}>
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="apple-data text-[10.5px] text-[var(--apple-blue-soft)]">{node.node_id}</span>
        <span className="text-[11.5px] text-[var(--apple-label)]">
          {node.assigned_role_template ? roleLabel(node.assigned_role_template) : '未指派模板'}
        </span>
        <Chip tone={parallel ? 'var(--apple-green)' : 'var(--apple-orange)'}>
          {parallel ? '可並行' : `串行 ← ${(node.depends_on ?? []).join(', ') || '—'}`}
        </Chip>
      </div>
      {node.description ? (
        <p className="mt-1 whitespace-pre-wrap break-words text-[11px] leading-relaxed text-[var(--apple-secondary)]">
          {node.description}
        </p>
      ) : null}
    </li>
  );
}


function AtomicSeatCard({ role, index }: { role: AtomicRoleInstance; index: number }) {
  const ref = formatRef(role.input_ref);
  return (
    <details className={LI_CLS}>
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-2">
        <span className="inline-block w-3 text-[var(--apple-tertiary)]" aria-hidden>
          ▸
        </span>
        <span className="apple-data text-[10.5px] text-[#bf5af2]">{role.instance_id || `seat-${index + 1}`}</span>
        <span className="text-[11.5px] text-[var(--apple-label)]">
          {role.name || role.template_id || role.trait || '原子席位'}
        </span>
        {role.node_id ? (
          <span className="apple-data text-[9.5px] text-[var(--apple-tertiary)]">@ {role.node_id}</span>
        ) : null}
        <span className="apple-data ml-auto text-[9.5px] text-[var(--apple-tertiary)]">
          {role.token_budget != null ? `${role.token_budget} tok` : '—'}・iter {role.max_iterations ?? '—'}
        </span>
      </summary>
      <div className="mt-2 space-y-2 border-t border-[var(--apple-hairline)] pt-2">
        <FieldGrid>
          <Field label="節點（node_id）" value={role.node_id} />
          <Field label="模板（template_id）" value={role.template_id} />
          <Field label="個性（trait）" value={role.trait} />
          <Field label="Token 預算（token_budget）" value={role.token_budget ?? '—'} />
          <Field label="最大迭代（max_iterations）" value={role.max_iterations ?? '—'} />
          <Field label="輸出格式（output_schema）" value={role.output_schema} />
          <Field label="輸入引用（input_ref）" wide value={ref} />
          <Field
            label="工具白名單（allowed_tools）"
            wide
            value={<ChipList items={listOf(role.allowed_tools)} tone="var(--apple-blue)" empty="無工具" />}
          />
          <Field
            label="成敗標準（success_criteria）"
            wide
            value={
              role.success_criteria ? (
                <span className="whitespace-pre-wrap break-words">{role.success_criteria}</span>
              ) : null
            }
          />
          <Field
            label="失敗退路（failure_fallback）"
            wide
            value={
              role.failure_fallback ? (
                <span className="whitespace-pre-wrap break-words">{role.failure_fallback}</span>
              ) : null
            }
          />
          <Field
            label="L0 偏置（l0_bias）"
            wide
            value={role.l0_bias ? <span className="whitespace-pre-wrap break-words">{role.l0_bias}</span> : null}
          />
        </FieldGrid>
        {role.system_prompt ? (
          <LongText text={role.system_prompt} label={`L2 孵化簡報（system_prompt）${role.trait ? `・${role.trait}` : ''}`} defaultOpen />
        ) : null}
      </div>
    </details>
  );
}

export default function PlanSection({ task }: { task: TaskProgress }) {
  const plan = planOf(task);
  const campaign = campaignOf(task);
  const battle = battlePlanOf(task);
  const commander = commanderOf(task);
  const execPlan = textField(plan?.execution_plan);
  const dagNodes = battle?.dag_nodes ?? [];
  const seats = battle?.atomic_role_instances ?? [];
  const hasAnything = Boolean(plan || campaign || battle || commander);

  return (
    <>
      <SectionHead
        index={3}
        title="作戰計劃"
        hint="Manager 分解 → L3 戰役地圖 → 原子作戰計劃"
        right={
          plan?.subtask_count != null ? (
            <span className="apple-data">{plan.subtask_count} 個子工作項</span>
          ) : null
        }
      />

      {!hasAnything ? (
        <EmptyState
          title="尚无作戰計劃產物"
          note="task.plan／raho.campaign／battle_plan 皆為空：任務尚未進入（或未走）公司運行時的規劃階段。"
        />
      ) : null}

      <SubHead>分解計劃（plan）</SubHead>
      {plan ? (
        <FieldGrid>
          <Field label="拆分子項數（subtask_count）" value={plan.subtask_count ?? '—'} />
          <Field label="拆解策略（strategy）" value={plan.strategy} />
          <Field
            label="執行計劃（execution_plan）"
            wide
            value={
              execPlan ? (
                <span className="whitespace-pre-wrap break-words">{execPlan}</span>
              ) : null
            }
          />
        </FieldGrid>
      ) : (
        <EmptyState title="尚無 Manager 分解記錄" note="task.plan 為空（decompose 階段尚未完成或未走公司路徑）。" />
      )}

      <SubHead count={campaign?.nodes?.length ?? 0}>戰役地圖（campaign）</SubHead>
      {campaign?.nodes?.length ? (
        <>
          {(campaign.goal || campaign.source) && (
            <Card className="mb-1.5">
              <div className="text-[11.5px] text-[var(--apple-label)]">{campaign.goal || '（未給戰役目標）'}</div>
              {campaign.source ? (
                <div className="apple-data mt-1 text-[9.5px] text-[var(--apple-tertiary)]">
                  來源：{campaign.source}
                </div>
              ) : null}
              {campaign.success_criteria?.length ? (
                <div className="mt-1.5">
                  <div className="mb-1 text-[9px] uppercase tracking-[0.06em] text-[var(--apple-tertiary)]">
                    戰役成敗標準
                  </div>
                  <ol className="space-y-0.5">
                    {campaign.success_criteria.map((c, i) => (
                      <li key={i} className="flex gap-1.5 text-[11px] leading-relaxed text-[var(--apple-secondary)]">
                        <span className="apple-data shrink-0">✓</span>
                        <span className="min-w-0 whitespace-pre-wrap break-words">{c}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
            </Card>
          )}
          <ul className="space-y-1.5">
            {campaign.nodes.map((node, i) => {
              const parallel = node.parallel_ok || !node.depends_on?.length;
              return (
                <li key={node.node_id || i} className={LI_CLS}>
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="apple-data text-[10.5px] text-[var(--apple-blue-soft)]">
                      {node.node_id || `N${i + 1}`}
                    </span>
                    <span className="text-[11.5px] text-[var(--apple-label)]">{node.title || '（未命名節點）'}</span>
                    <Chip tone={parallel ? 'var(--apple-green)' : 'var(--apple-orange)'}>
                      {parallel ? '可並行' : `串行 ← ${(node.depends_on ?? []).join(', ')}`}
                    </Chip>
                  </div>
                  {node.outcome ? (
                    <p className="mt-1 whitespace-pre-wrap break-words text-[11px] leading-relaxed text-[var(--apple-secondary)]">
                      產出：{node.outcome}
                    </p>
                  ) : null}
                  {node.success_criteria ? (
                    <p className="mt-1 whitespace-pre-wrap break-words text-[11px] leading-relaxed text-[var(--apple-green)]">
                      驗收：{node.success_criteria}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </>
      ) : campaign ? (
        <JsonBlock value={campaign} label="戰役地圖原始 JSON" />
      ) : (
        <EmptyState title="尚無戰役地圖" note="campaign 未產出：L3 戰術指揮官尚未下達戰役節點。" />
      )}

      <SubHead count={dagNodes.length}>原子作戰計劃（battle_plan）</SubHead>
      {battle ? (
        <>
          <Card>
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5">
              <span className="apple-data text-[10.5px] text-[var(--apple-label)]">
                {battle.plan_id || '（無 plan_id）'}
              </span>
              {battle.rush_mode ? <Chip tone="var(--apple-orange)">極速模式</Chip> : null}
              <span className="apple-data text-[10px] text-[var(--apple-secondary)]">
                串行深度 {battle.serial_depth ?? '—'}・並行根 {(battle.parallel_roots ?? []).length || '—'}
              </span>
              <span className="apple-data text-[10px] text-[var(--apple-secondary)]">
                並行工人 {battle.global_settings?.max_parallel_workers ?? '—'}・逾時{' '}
                {battle.global_settings?.global_timeout_minutes ?? '—'} 分
                {battle.global_settings?.default_model ? `・${battle.global_settings.default_model}` : ''}
              </span>
            </div>
            {battle.based_on_l4_json ? (
              <LongText text={battle.based_on_l4_json} label="依據的 L4 門票 JSON（based_on_l4_json）" />
            ) : null}
          </Card>

          {dagNodes.length ? (
            <>
              <div className="mb-1 mt-2 text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--apple-tertiary)]">
                DAG 節點（dag_nodes）
              </div>
              <ul className="space-y-1.5">
                {dagNodes.map((node, i) => (
                  <DagNodeRow key={node.node_id || i} node={node} />
                ))}
              </ul>
            </>
          ) : null}

          {seats.length ? (
            <>
              <div className="mb-1 mt-2 text-[9px] font-semibold uppercase tracking-[0.06em] text-[var(--apple-tertiary)]">
                原子席位編制（atomic_role_instances）・{seats.length} 席
              </div>
              <ul className="space-y-1.5">
                {seats.map((role, i) => (
                  <AtomicSeatCard key={role.instance_id || i} role={role} index={i} />
                ))}
              </ul>
            </>
          ) : null}

          <JsonBlock value={battle.reasoning} label="作戰推理（reasoning）" />

          <SubHead>指揮官快照（commander）</SubHead>
          {commander ? (
            <JsonBlock value={commander} label="L3 指揮官席位的回報原始 JSON" />
          ) : (
            <p className="text-[10.5px] text-[var(--apple-tertiary)]">
              raho.commander 未隨本快照回傳（可在席位 I/O 監察整頁查全文）。
            </p>
          )}
        </>
      ) : (
        <EmptyState
          title="尚無原子作戰計劃"
          note="raho.battle_plan 為空：L3 戰術指揮官尚未完成拆解，或任務未達 RAHO 複雜度門檻。"
        />
      )}
    </>
  );
}
