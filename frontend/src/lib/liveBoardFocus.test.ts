import { describe, expect, it } from 'vitest';
import type { AnimLiveFeed } from './animLive';
import {
  buildWorkflowSteps,
  collectLiveAnomalies,
  pickNextWorkflowStep,
} from './liveBoardFocus';

const baseFeed: AnimLiveFeed = {
  runningTasks: 0,
  agents: [],
  live: false,
  llmOps: {
    configured: false,
    api_routes: [],
    allowed_models: [],
    route_strategy: 'role_preferred',
  } as unknown as NonNullable<AnimLiveFeed['llmOps']>,
};

describe('liveBoardFocus', () => {
  it('picks API step when nothing configured', () => {
    const steps = buildWorkflowSteps(baseFeed);
    expect(pickNextWorkflowStep(steps)?.label).toBe('配置 API');
  });

  it('collects offline and api anomalies', () => {
    const anomalies = collectLiveAnomalies({
      feed: baseFeed,
      connected: false,
      unhealthyKeys: 2,
      capacityFull: false,
    });
    expect(anomalies.some((a) => a.id === 'offline')).toBe(true);
    expect(anomalies.some((a) => a.id === 'billing-keys')).toBe(true);
    expect(anomalies.some((a) => a.id === 'api-missing')).toBe(true);
  });

  it('skips api-missing when routes enabled', () => {
    const feed: AnimLiveFeed = {
      ...baseFeed,
      llmOps: {
        configured: true,
        api_routes: [
          {
            id: 'x',
            name: 'X',
            configured: true,
            enabled: true,
            allowed_models: [],
            model: 'm',
          },
        ],
        allowed_models: [],
        route_strategy: 'role_preferred',
      } as unknown as NonNullable<AnimLiveFeed['llmOps']>,
    };
    const anomalies = collectLiveAnomalies({
      feed,
      connected: true,
      unhealthyKeys: 0,
      capacityFull: false,
    });
    expect(anomalies.some((a) => a.id === 'api-missing')).toBe(false);
  });
});
