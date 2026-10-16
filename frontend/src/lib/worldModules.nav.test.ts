import { describe, expect, it } from 'vitest';
import {
  MINECRAFT_NAV_DEFAULT_OPEN_GROUP_IDS,
  minecraftNavGroupCount,
  resolveModulePage,
} from './worldModules';

describe('Minecraft nav contract', () => {
  it('uses fewer than 7 sidebar groups', () => {
    expect(minecraftNavGroupCount()).toBeLessThan(7);
    expect(minecraftNavGroupCount()).toBe(5);
  });

  it('defaults accordion to field overview only', () => {
    expect(MINECRAFT_NAV_DEFAULT_OPEN_GROUP_IDS.has('field_overview')).toBe(true);
    expect(MINECRAFT_NAV_DEFAULT_OPEN_GROUP_IDS.size).toBe(1);
  });

  it('keeps deep-link aliases', () => {
    expect(resolveModulePage('overview')).toBe('monitor');
    expect(resolveModulePage('bridge')).toBe('minecraft');
    expect(resolveModulePage('bridge_health')).toBe('bridge_monitor');
    expect(resolveModulePage('dynmap')).toBe('server-map');
  });
});
