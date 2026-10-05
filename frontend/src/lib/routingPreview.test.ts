import { describe, expect, it } from 'vitest';
import { shouldRunGrill, usesTaskWorkspace } from './routingPreview';
import type { RoutingPreview } from '../types';

const companyPreview: RoutingPreview = {
  path: 'company',
  template: 'story_studio',
  complexity: 'medium',
  tier: 'medium',
  model_hint: 'x',
  max_reflection_rounds: 0,
  reason_codes: [],
  estimated_cost: { level: 'high', est_tokens: 12000 },
};

describe('routingPreview helpers', () => {
  it('usesTaskWorkspace for company strategy and opc preview', () => {
    expect(usesTaskWorkspace('company', null)).toBe(true);
    expect(usesTaskWorkspace('simple', companyPreview)).toBe(false);
    expect(usesTaskWorkspace('auto', { ...companyPreview, path: 'opc' })).toBe(true);
    expect(usesTaskWorkspace('auto', { ...companyPreview, path: 'minecraft_ops' })).toBe(false);
  });

  it('shouldRunGrill only for company path', () => {
    expect(shouldRunGrill('auto', companyPreview)).toBe(true);
    expect(shouldRunGrill('auto', { ...companyPreview, path: 'simple' })).toBe(false);
    expect(shouldRunGrill('simple', companyPreview)).toBe(false);
  });
});
