import { describe, expect, it } from 'vitest';
import { TASK_COLUMNS, taskColumnKey, tasksInColumn } from './agentUi';

describe('TASK_COLUMNS bucketing', () => {
  const sample = [
    { status: 'pending', id: '1' },
    { status: 'running', id: '2' },
    { status: 'completed', id: '3' },
    { status: 'failed', id: '4' },
    { status: 'cancelled', id: '5' },
    { status: 'interrupted', id: '6' },
  ];

  it('maps only completed to done column', () => {
    expect(taskColumnKey('completed')).toBe('done');
    expect(taskColumnKey('cancelled')).toBe('failed');
    expect(taskColumnKey('interrupted')).toBe('failed');
    expect(taskColumnKey('failed')).toBe('failed');
  });

  it('does not put cancelled or interrupted in done column', () => {
    const done = tasksInColumn(sample, 'done');
    const failed = tasksInColumn(sample, 'failed');
    expect(done).toHaveLength(1);
    expect(done[0].id).toBe('3');
    expect(failed).toHaveLength(3);
    expect(TASK_COLUMNS.find((c) => c.key === 'done')?.statuses).toEqual(['completed']);
  });
});
