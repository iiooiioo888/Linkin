import { describe, expect, it } from 'vitest';
import {
  TERMINAL_TASK_STATUSES,
  coerceTaskProgressStatus,
  isLiveMonitorTask,
  isTerminalTaskStatus,
  looksLikeCompanyQuery,
} from './chatWorkspace';

describe('looksLikeCompanyQuery', () => {
  it('matches linkin and minecraft heuristics', () => {
    expect(looksLikeCompanyQuery('在灵境精灵森林建造一座树桥聚落')).toBe(true);
    expect(looksLikeCompanyQuery('在坐标(100, 64, 200)处放置一个钻石块')).toBe(true);
    expect(looksLikeCompanyQuery('今天天氣如何')).toBe(false);
  });
});

describe('task terminal status helpers', () => {
  it('treats cancelled and interrupted as terminal', () => {
    expect(isTerminalTaskStatus('cancelled')).toBe(true);
    expect(isTerminalTaskStatus('interrupted')).toBe(true);
    expect(isTerminalTaskStatus('running')).toBe(false);
    expect(TERMINAL_TASK_STATUSES.has('cancelled')).toBe(true);
    expect(TERMINAL_TASK_STATUSES.has('interrupted')).toBe(true);
  });

  it('coerceTaskProgressStatus preserves cancelled/interrupted', () => {
    expect(coerceTaskProgressStatus('cancelled')).toBe('cancelled');
    expect(coerceTaskProgressStatus('interrupted')).toBe('interrupted');
    expect(coerceTaskProgressStatus('bogus', 'failed')).toBe('failed');
  });

  it('isLiveMonitorTask is false for cancelled terminal messages', () => {
    expect(
      isLiveMonitorTask({
        taskId: 't1',
        streaming: false,
        taskState: {
          task_id: 't1',
          status: 'cancelled',
          strategy: 'company',
          template: 'quick_task',
          query: 'q',
          phase: 'execute',
          iteration: 0,
          score: null,
          answer: '',
          error: '',
          events: [],
          kanban: {},
          budget: {},
          resolved_path: 'company',
        },
      }),
    ).toBe(false);
  });
});
