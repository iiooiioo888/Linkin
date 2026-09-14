import { describe, expect, it } from 'vitest';
import { formatPercentKpiParts, formatPercentLabel, normalizePercentNumber } from './formatMetrics';

describe('formatMetrics', () => {
  it('normalizePercentNumber strips trailing percent signs', () => {
    expect(normalizePercentNumber('33.3%')).toBe(33.3);
    expect(normalizePercentNumber('33.3%%')).toBe(33.3);
    expect(normalizePercentNumber(42)).toBe(42);
  });

  it('formatPercentLabel never emits double percent', () => {
    expect(formatPercentLabel('33.3%%')).toBe('33.3%');
    expect(formatPercentLabel(0)).toBe('0%');
  });

  it('formatPercentKpiParts keeps unit separate from numeric value', () => {
    expect(formatPercentKpiParts('33.3%')).toEqual({ value: '33.3', unit: '%' });
  });
});
