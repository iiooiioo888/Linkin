import type { BattlePlanState } from '../types';

/** 審計通過後 trigger_planner 產物是否足以跳過第二次 planBattle。 */
export function hasReusablePlanner(planner: Record<string, unknown> | null | undefined): boolean {
  if (!planner || String(planner.status || '') !== 'PLANNER_TRIGGERED') {
    return false;
  }
  const commander = planner.commander;
  if (!commander || typeof commander !== 'object') {
    return false;
  }
  const status = String((commander as Record<string, unknown>).status || '');
  if (status === 'PLAN_READY' && (commander as Record<string, unknown>).battle_plan) {
    return true;
  }
  return status === 'REJECT_TO_L4' || status === 'ESCALATE_TO_USER';
}

export function battleFromPlanner(
  planner: Record<string, unknown> | null | undefined,
): BattlePlanState | null {
  if (!planner?.commander || typeof planner.commander !== 'object') {
    return null;
  }
  return planner.commander as BattlePlanState;
}

export function battleBlocked(battle: BattlePlanState | null | undefined): boolean {
  if (!battle) return false;
  return battle.status === 'REJECT_TO_L4' || battle.status === 'ESCALATE_TO_USER';
}
