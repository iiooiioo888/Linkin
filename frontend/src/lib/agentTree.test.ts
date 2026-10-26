import { describe, expect, it } from 'vitest';
import { AGENT_STATUS_META, blankMetrics } from './agentUi';
import {
  ancestorOpenIds,
  buildAgentExecutionTree,
  defaultOpenIds,
  filterAgentTree,
  focusAgentTree,
  mapRoleStatus,
  mapWorkStatus,
  summarizeAgentTree,
} from './agentTree';
import type { AgentWorkItem, RoleAgent } from '../types';

function role(partial: Partial<RoleAgent> & Pick<RoleAgent, 'id' | 'name'>): RoleAgent {
  return {
    level: 1,
    level_label: '層級',
    category: 'management',
    reporting_to: null,
    can_delegate_to: [],
    direct_reports: [],
    responsibilities: [],
    max_parallel_work: 1,
    default_tier: 'routine',
    templates: [],
    status: 'idle',
    inbox: {},
    queue: 0,
    executing: 0,
    done: 0,
    blocked: 0,
    cost_usd: 0,
    last_activity_at: null,
    work_items: [],
    events: [],
    active_task_ids: [],
    current_item: null,
    company_tasks: [],
    capacity_used: 0,
    metrics: blankMetrics(),
    ...partial,
  };
}

function work(partial: Partial<AgentWorkItem> & Pick<AgentWorkItem, 'id' | 'status'>): AgentWorkItem {
  return {
    title: partial.title ?? partial.id,
    description: '',
    kind: 'assigned',
    assignee: null,
    task_id: 'task-1',
    task_query: '',
    task_status: '',
    phase: '',
    cost_usd: 0,
    output_preview: '',
    updated_at: null,
    source: 'live',
    ...partial,
  };
}

describe('mapRoleStatus', () => {
  it('maps monitor statuses onto tree keys and keeps AGENT_STATUS_META labels', () => {
    expect(mapRoleStatus({ status: 'busy', enabled: true })).toEqual({
      status: 'running',
      label: AGENT_STATUS_META.busy.label,
    });
    expect(mapRoleStatus({ status: 'waiting' })).toEqual({
      status: 'waiting',
      label: AGENT_STATUS_META.waiting.label,
    });
    expect(mapRoleStatus({ status: 'error' })).toEqual({
      status: 'failed',
      label: AGENT_STATUS_META.error.label,
    });
    expect(mapRoleStatus({ status: 'idle' })).toEqual({
      status: 'idle',
      label: AGENT_STATUS_META.idle.label,
    });
    expect(mapRoleStatus({ status: 'disabled' })).toEqual({
      status: 'disabled',
      label: AGENT_STATUS_META.disabled.label,
    });
  });

  it('does not invent queued, done, or stopped for unknown role status', () => {
    expect(mapRoleStatus({ status: 'mystery' })).toEqual({
      status: 'idle',
      label: AGENT_STATUS_META.idle.label,
    });
  });

  it('treats enabled false as disabled even if status is still busy', () => {
    expect(mapRoleStatus({ status: 'busy', enabled: false }).status).toBe('disabled');
  });
});

describe('mapWorkStatus', () => {
  it('maps backend work and task statuses, including queued done and stopped', () => {
    expect(mapWorkStatus('planning')?.status).toBe('queued');
    expect(mapWorkStatus('ready')?.status).toBe('queued');
    expect(mapWorkStatus('pending')?.status).toBe('queued');
    expect(mapWorkStatus('executing')).toEqual({ status: 'running', label: '執行中' });
    expect(mapWorkStatus('running')?.status).toBe('running');
    expect(mapWorkStatus('in_review')?.status).toBe('waiting');
    expect(mapWorkStatus('blocked')).toEqual({ status: 'failed', label: AGENT_STATUS_META.error.label });
    expect(mapWorkStatus('failed')).toEqual({ status: 'failed', label: '失敗' });
    expect(mapWorkStatus('done')).toEqual({ status: 'done', label: '已完成' });
    expect(mapWorkStatus('completed')?.status).toBe('done');
    expect(mapWorkStatus('cancelled')).toEqual({ status: 'stopped', label: '已停止' });
    expect(mapWorkStatus('interrupted')?.status).toBe('stopped');
  });

  it('returns null for statuses the backend does not emit', () => {
    expect(mapWorkStatus('not-a-status')).toBeNull();
    expect(mapWorkStatus('')).toBeNull();
  });
});

describe('buildAgentExecutionTree', () => {
  const manager = role({
    id: 'manager',
    name: '任務經理',
    level: 0,
    level_label: '最高決策層',
    raho_short: 'L4 任務經理',
    status: 'busy',
    executing: 1,
    direct_reports: ['tech_lead', 'stray'],
    work_items: [work({ id: 'w-live', title: '拆解需求', status: 'executing', phase: 'decompose' })],
  });
  const lead = role({
    id: 'tech_lead',
    name: '技術主管',
    level: 1,
    reporting_to: 'manager',
    direct_reports: ['frontend'],
    status: 'waiting',
    queue: 1,
    work_items: [
      work({ id: 'w-queue', title: '排隊項', status: 'planning', task_id: 't-q' }),
      work({ id: 'w-done', title: '已完成項', status: 'done', task_id: 't-d' }),
      work({ id: 'w-stop', title: '已取消項', status: 'cancelled', task_id: 't-c' }),
    ],
  });
  const engineer = role({
    id: 'frontend',
    name: '前端',
    level: 2,
    reporting_to: 'tech_lead',
    status: 'error',
    blocked: 1,
    work_items: [work({ id: 'w-block', title: '被擋住', status: 'blocked', kind: 'review' })],
  });
  const orphan = role({
    id: 'stray',
    name: '游離席',
    level: 3,
    reporting_to: 'missing-boss',
    status: 'idle',
  });
  const disabled = role({
    id: 'old',
    name: '停用席',
    level: 4,
    reporting_to: null,
    status: 'idle',
    enabled: false,
  });

  const tree = buildAgentExecutionTree([engineer, orphan, disabled, lead, manager]);

  it('nests reporting_to and falls back to direct_reports when the parent id is outside the roster', () => {
    expect(tree.map((node) => node.roleId)).toEqual(['manager', 'old']);
    const managerNode = tree[0];
    expect(managerNode.children.filter((node) => node.kind === 'role').map((node) => node.roleId)).toEqual([
      'tech_lead',
      'stray',
    ]);
    const leadNode = managerNode.children.find((node) => node.roleId === 'tech_lead');
    expect(leadNode?.children.filter((node) => node.kind === 'role').map((node) => node.roleId)).toEqual(['frontend']);
  });

  it('nests only active work and keeps done or stopped off the tree', () => {
    const managerWork = tree[0].children.filter((node) => node.kind === 'work');
    expect(managerWork.map((node) => node.label)).toEqual(['拆解需求']);
    expect(managerWork[0].status).toBe('running');

    const leadNode = tree[0].children.find((node) => node.roleId === 'tech_lead')!;
    const leadWork = leadNode.children.filter((node) => node.kind === 'work');
    expect(leadWork.map((node) => node.status)).toEqual(['queued']);
    expect(leadWork.some((node) => node.label === '已完成項' || node.label === '已取消項')).toBe(false);

    const front = leadNode.children.find((node) => node.roleId === 'frontend');
    expect(front?.children[0]).toMatchObject({ kind: 'work', status: 'failed', statusLabel: '阻塞' });
  });

  it('uses a company task only when that task has no work item yet', () => {
    const solo = role({
      id: 'solo',
      name: '獨行',
      company_tasks: [{ task_id: 'c1', query: '盤點庫存', status: 'running', phase: 'execute' }],
    });
    const covered = role({
      id: 'covered',
      name: '已有工作項',
      company_tasks: [{ task_id: 't-q', query: '不應重複', status: 'running', phase: 'execute' }],
      work_items: [work({ id: 'already', title: '已掛上', status: 'executing', task_id: 't-q' })],
    });
    const nodes = buildAgentExecutionTree([solo, covered]);
    expect(nodes.find((node) => node.roleId === 'solo')?.children.map((node) => node.label)).toEqual(['盤點庫存']);
    expect(nodes.find((node) => node.roleId === 'covered')?.children.map((node) => node.label)).toEqual(['已掛上']);
  });

  it('breaks reporting cycles without dropping seats', () => {
    const a = role({ id: 'a', name: '甲', reporting_to: 'b', level: 1 });
    const b = role({ id: 'b', name: '乙', reporting_to: 'a', level: 1 });
    const nodes = buildAgentExecutionTree([a, b]);
    const ids = nodes.flatMap(function walk(node): string[] {
      return [node.roleId, ...node.children.filter((child) => child.kind === 'role').flatMap(walk)];
    });
    expect(new Set(ids)).toEqual(new Set(['a', 'b']));
    expect(ids).toHaveLength(2);
    expect(nodes).toHaveLength(1);
  });

  it('summarizes role execution and counts nested work', () => {
    expect(summarizeAgentTree(tree)).toMatchObject({
      roles: 5,
      running: 1,
      waiting: 1,
      failed: 1,
      disabled: 1,
      idle: 1,
      work: 3,
    });
  });

  it('opens roots and live seats by default, and opens the path to the selected seat', () => {
    expect(defaultOpenIds(tree)).toEqual(expect.arrayContaining(['role:manager', 'role:tech_lead', 'role:frontend']));
    expect(defaultOpenIds(tree)).not.toContain('role:old');
    expect(ancestorOpenIds(tree, 'frontend')).toEqual(['role:manager', 'role:tech_lead', 'role:frontend']);
  });
});

describe('filter and focus', () => {
  const tree = buildAgentExecutionTree([
    role({
      id: 'manager',
      name: '任務經理',
      level: 0,
      status: 'idle',
      direct_reports: ['busy', 'calm'],
    }),
    role({
      id: 'busy',
      name: '忙碌席',
      level: 2,
      reporting_to: 'manager',
      status: 'busy',
      work_items: [work({ id: 'run', title: '正在寫', status: 'executing' })],
    }),
    role({ id: 'calm', name: '安靜席', level: 2, reporting_to: 'manager', status: 'idle' }),
  ]);

  it('keeps ancestors when a descendant matches the query', () => {
    const filtered = filterAgentTree(tree, '正在寫');
    expect(filtered).toHaveLength(1);
    expect(filtered[0].roleId).toBe('manager');
    expect(filtered[0].children.map((node) => node.roleId)).toEqual(['busy']);
    expect(filtered[0].children[0].children.map((node) => node.label)).toEqual(['正在寫']);
  });

  it('focuses the live path and drops idle branches', () => {
    const live = focusAgentTree(tree, 'live');
    expect(live[0].children.map((node) => node.roleId)).toEqual(['busy']);
    expect(live[0].children[0].children[0].status).toBe('running');
  });
});
