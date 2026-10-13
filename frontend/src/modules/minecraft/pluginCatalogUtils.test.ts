import { describe, expect, it } from 'vitest';
import { formatPlatformsLabel, normalizeStringList } from './pluginCatalogUtils';

describe('normalizeStringList', () => {
  it('accepts arrays', () => {
    expect(normalizeStringList(['Paper', 'Spigot'])).toEqual(['Paper', 'Spigot']);
  });

  it('wraps a single platform string (bad API shape)', () => {
    expect(normalizeStringList('Paper')).toEqual(['Paper']);
  });

  it('handles null and empty', () => {
    expect(normalizeStringList(null)).toEqual([]);
    expect(normalizeStringList('')).toEqual([]);
    expect(normalizeStringList([])).toEqual([]);
  });
});

describe('formatPlatformsLabel', () => {
  it('joins normalized platforms', () => {
    expect(formatPlatformsLabel('Paper')).toBe('Paper');
    expect(formatPlatformsLabel(['Spigot', 'Paper'])).toBe('Spigot · Paper');
  });

  it('shows dash when missing', () => {
    expect(formatPlatformsLabel(null)).toBe('—');
  });
});
