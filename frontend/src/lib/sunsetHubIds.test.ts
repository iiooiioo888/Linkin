import { describe, expect, it } from 'vitest';
import {
  SUNSET_HUB_IDS,
  collectSunsetModelRefs,
  filterSelectableHubIds,
  filterSelectableHubModels,
  isSunsetHubId,
  markSunsetHubModelsUnavailable,
} from './sunsetHubIds';

describe('sunsetHubIds', () => {
  it('lists exactly nine path-B sunset hub ids', () => {
    expect(SUNSET_HUB_IDS).toHaveLength(9);
    expect(new Set(SUNSET_HUB_IDS).size).toBe(9);
  });

  it('isSunsetHubId matches only the nine keys', () => {
    expect(isSunsetHubId('gpt-5.6-sol')).toBe(true);
    expect(isSunsetHubId('kimi-k3')).toBe(true);
    expect(isSunsetHubId('gpt-5.6-terra')).toBe(false);
    expect(isSunsetHubId('deepseek-v4-pro')).toBe(false);
    expect(isSunsetHubId('')).toBe(false);
    expect(isSunsetHubId(undefined)).toBe(false);
  });

  it('filterSelectableHubIds drops sunset defaults', () => {
    expect(
      filterSelectableHubIds(['gpt-5.6-sol', 'gpt-5.6-terra', 'deepseek-v4-flash', 'qwen3.8-flash']),
    ).toEqual(['gpt-5.6-terra', 'qwen3.8-flash']);
  });

  it('filterSelectableHubModels drops sunset models from picker pools', () => {
    const pool = [{ id: 'gpt-5.6-sol' }, { id: 'gpt-5.6-terra' }, { id: 'glm-5.3' }];
    expect(filterSelectableHubModels(pool).map((m) => m.id)).toEqual(['gpt-5.6-terra']);
  });

  it('markSunsetHubModelsUnavailable sets available_in_pool false', () => {
    const marked = markSunsetHubModelsUnavailable([
      { id: 'gpt-5.6-sol', available_in_pool: true },
      { id: 'gpt-5.6-terra', available_in_pool: true },
    ]);
    expect(marked[0].available_in_pool).toBe(false);
    expect(marked[1].available_in_pool).toBe(true);
  });

  it('collectSunsetModelRefs finds preferred and failover hits', () => {
    expect(
      collectSunsetModelRefs({
        preferred_model: 'gpt-5.6-sol',
        failover_models: ['gpt-5.6-terra', 'kimi-k3', 'gemini-3.1-pro'],
      }),
    ).toEqual(['gpt-5.6-sol', 'kimi-k3', 'gemini-3.1-pro']);
    expect(collectSunsetModelRefs({ preferred_model: 'gpt-5.6-terra', failover_models: [] })).toEqual(
      [],
    );
  });
});

import { PROVIDER_PRESETS } from '../components/ApiRoutesEditor';

describe('PROVIDER_PRESETS vs sunset', () => {
  it('defaultModel and models do not push sunset hub ids as selectable', () => {
    for (const preset of PROVIDER_PRESETS) {
      expect(isSunsetHubId(preset.defaultModel), `${preset.value} defaultModel`).toBe(false);
      for (const mid of preset.models) {
        expect(isSunsetHubId(mid), `${preset.value} model ${mid}`).toBe(false);
      }
    }
  });
});
