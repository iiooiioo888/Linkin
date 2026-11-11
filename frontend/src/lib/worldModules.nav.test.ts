import { describe, expect, it } from 'vitest';
import { BUILTIN_WORLD_MODULES, listWorldModules, resolveModulePage } from './worldModules';

describe('world module catalog', () => {
  it('has no builtin Minecraft module', () => {
    expect(BUILTIN_WORLD_MODULES.find((item) => item.id === 'minecraft')).toBeUndefined();
    expect(listWorldModules().some((item) => item.id === 'minecraft')).toBe(false);
  });

  it('does not resolve legacy Minecraft page aliases', () => {
    expect(resolveModulePage('bridge')).toBeNull();
    expect(resolveModulePage('dynmap')).toBeNull();
    expect(resolveModulePage('overview')).toBeNull();
  });
});
