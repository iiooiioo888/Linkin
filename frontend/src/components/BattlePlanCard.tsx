/**
 * BattlePlanCard — L3 戰術指揮官：原子作戰地圖 / 退回 / 上交。
 */
import type { AtomicRoleInstance, BattlePlanState } from '../types';
import { L0BiasHint } from './L0BiasHint';

interface BattlePlanCardProps {
  battle: BattlePlanState;
  onPickAlternative?: (choice: string) => void;
}

function formatRef(ref?: string | string[]) {
  if (!ref) return '';
  return Array.isArray(ref) ? ref.join(' · ') : ref;
}

function RoleBrief({ role }: { role: AtomicRoleInstance }) {
  const ref = formatRef(role.input_ref);
  return (
    <>
      <code>
        tools: {(role.allowed_tools ?? []).join(', ') || '—'} · {role.token_budget} tok · iter{' '}
        {role.max_iterations}
        {role.output_schema ? ` · ${role.output_schema}` : ''}
        {role.success_criteria ? ` · 成敗：${role.success_criteria}` : ''}
        {role.l0_bias ? `\nL0：${role.l0_bias}` : ''}
        {ref ? `\nref: ${ref}` : ''}
      </code>
      {role.system_prompt ? (
        <details className="raho-battle-prompt">
          <summary>L2 孵化簡報{role.trait ? ` · ${role.trait}` : ''}</summary>
          <pre>{role.system_prompt}</pre>
        </details>
      ) : null}
    </>
  );
}

export default function BattlePlanCard({ battle, onPickAlternative }: BattlePlanCardProps) {
  const status = battle.status || '';
  const rejected = status === 'REJECT_TO_L4';
  const escalated = status === 'ESCALATE_TO_USER';
  const ready = status === 'PLAN_READY';
  const plan = battle.battle_plan;
  const nodes = plan?.dag_nodes ?? [];
  const roles = plan?.atomic_role_instances ?? [];
  const checks = battle.checklist?.items ?? [];
  const serial = battle.serial_depth ?? plan?.serial_depth;
  const parallelRoots = plan?.parallel_roots?.length ?? nodes.filter((n) => !n.depends_on?.length).length;
  const cot = battle.reasoning || plan?.reasoning;
  const topo = cot?.topology;
  const templates = (cot?.templating ?? [])
    .map((row) => `${row.node_id || ''} ${row.name || row.template || ''}`.trim())
    .filter(Boolean)
    .join(' · ');
  const budgets = (cot?.budgeting ?? [])
    .map((row) => `${row.instance_id} ${row.max_iterations}iter/${row.token_budget}tok`)
    .join(' · ');

  return (
    <div
      className={`raho-battle-card${rejected ? ' is-failed' : ''}${escalated ? ' is-escalate' : ''}${ready ? ' is-ready' : ''}`}
    >
      <div className="raho-grill-head">
        <span className="raho-battle-kicker">{battle.role_label || 'L3 戰術指揮官'}</span>
        <span>
          {rejected
            ? '退回 L4'
            : escalated
              ? '上交 L5'
              : ready
                ? battle.rush_mode
                  ? '極速模式'
                  : '作戰地圖就緒'
                : status}
        </span>
      </div>
      <p className="raho-grill-lead">
        {rejected
          ? '門票缺件，拒絕拆解。請需求審計官補齊受詞或絕對不做清單。'
          : escalated
            ? '約束內不可行，禁止硬拆。請選擇替代方案。'
            : `${battle.node_count ?? nodes.length} 個原子節點 · 並行根 ${parallelRoots} · 串行深度 ${serial ?? '—'} · L2 簡報 < 200 Token · 微雕與偏執`}
      </p>
      <L0BiasHint snapshot={battle.l0} compact />

      {checks.length > 0 && (
        <ul className="raho-battle-checks">
          {checks.map((item) => (
            <li key={item.id} className={item.pass ? 'is-pass' : 'is-fail'}>
              {item.pass ? '通過' : '缺件'} · {item.label}
              {item.rush_mode ? ' · 已標極速' : ''}
            </li>
          ))}
        </ul>
      )}

      {ready && cot ? (
        <ol className="raho-battle-cot">
          <li>
            解析 · {cot.parsing?.core_action || '已掃描 L4 JSON'}
            {cot.parsing?.absolute_exclusions?.length
              ? ` · 排除 ${cot.parsing.absolute_exclusions.length} 項`
              : ''}
          </li>
          <li>
            拓撲 · 並行 {(topo?.parallel ?? []).join(', ') || '—'} · 串行{' '}
            {(topo?.sequential ?? []).join(', ') || '—'} · 深度 {topo?.serial_depth ?? '—'}
          </li>
          <li>模板 · {templates || '微型角色已匹配'}</li>
          <li>預算 · {budgets || '已分配迭代與 Token 帽'}</li>
        </ol>
      ) : null}

      {rejected && (battle.defects ?? []).length > 0 && (
        <ul className="raho-battle-defects">
          {(battle.defects ?? []).map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
      )}

      {escalated && (
        <div>
          <p className="raho-battle-details">{battle.details || battle.reason}</p>
          <div className="raho-grill-actions">
            {(battle.suggested_alternatives ?? []).map((alt) => (
              <button
                key={alt}
                type="button"
                className="raho-btn"
                onClick={() => onPickAlternative?.(alt)}
              >
                {alt}
              </button>
            ))}
          </div>
        </div>
      )}

      {ready && nodes.length > 0 && (
        <ol className="raho-battle-dag">
          {nodes.map((node) => {
            const role = roles.find((r) => r.node_id === node.node_id);
            const parallel = node.parallel_ok || !node.depends_on?.length;
            const deps = parallel ? '可並行啟動' : `串行 ← ${node.depends_on?.join(', ')}`;
            return (
              <li key={node.node_id}>
                <strong>
                  {node.node_id} · {role?.name || node.assigned_role_template || 'generic'}
                  {parallel ? ' · 並行' : ' · 串行'}
                </strong>
                <span>{node.description}</span>
                <em>{deps}</em>
                {role ? <RoleBrief role={role} /> : null}
              </li>
            );
          })}
        </ol>
      )}

      {ready && plan?.plan_id ? (
        <pre className="raho-ticket">
          {plan.plan_id} · {plan.based_on_l4_json}
          {'\n'}
          並行 {plan.global_settings?.max_parallel_workers ?? 5} · 逾時{' '}
          {plan.global_settings?.global_timeout_minutes ?? 120} 分
          {plan.global_settings?.default_model ? ` · ${plan.global_settings.default_model}` : ''}
        </pre>
      ) : null}

      {ready && battle.battle_plan_yaml ? (
        <details className="raho-battle-yaml">
          <summary>戰鬥指令 YAML（作戰手冊）</summary>
          <pre>{battle.battle_plan_yaml}</pre>
        </details>
      ) : null}
    </div>
  );
}
