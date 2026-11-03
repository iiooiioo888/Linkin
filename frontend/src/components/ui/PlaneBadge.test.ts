import { describe, expect, it } from 'vitest';
import { planeKindForActivity } from './PlaneBadge';

describe('planeKindForActivity', () => {
  it('maps compute/supply/assets planes', () => {
    expect(planeKindForActivity('compute')).toBe('ai-core');
    expect(planeKindForActivity('supply')).toBe('cloud-core');
    expect(planeKindForActivity('assets')).toBe('assets');
  });

  it('returns null for non-plane activities', () => {
    expect(planeKindForActivity('work')).toBeNull();
    expect(planeKindForActivity('observe')).toBeNull();
    expect(planeKindForActivity('world')).toBeNull();
    expect(planeKindForActivity('settings')).toBeNull();
  });
});
