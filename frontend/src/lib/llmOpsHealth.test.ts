import { describe, expect, it } from 'vitest';
import type { ApiRoutePublic, LlmOpsData } from '../types';
import { isAuthCatalogError, llmOpsHealthLabel, routeProbeTone } from './llmOpsHealth';

function route(partial: Partial<ApiRoutePublic>): ApiRoutePublic {
  return {
    id: 'r1',
    name: 'Test',
    provider: 'token-plan',
    provider_label: 'Token Plan',
    api_key: 'sk-***',
    configured: true,
    api_base: 'https://example.com/v1',
    model: 'qwen3.8-flash',
    allowed_models: ['qwen3.8-flash'],
    catalog: [],
    catalog_source: 'static',
    catalog_error: '',
    catalog_fetched_at: '',
    catalog_url: '',
    weight: 10,
    enabled: true,
    fallback: false,
    is_default: true,
    ...partial,
  };
}

describe('llmOpsHealth', () => {
  it('detects auth catalog errors', () => {
    expect(isAuthCatalogError('HTTP Error 401: Unauthorized')).toBe(true);
    expect(isAuthCatalogError('目錄為空，改用靜態清單')).toBe(false);
  });

  it('marks route with 401 as auth tone', () => {
    expect(
      routeProbeTone(route({ catalog_error: 'HTTP Error 401: Unauthorized' })),
    ).toBe('auth');
  });

  it('shows auth failure in ops health when consecutive_fail is zero', () => {
    const data = {
      ops: {
        refresh_interval_sec: 300,
        last_ok_at: '',
        last_error: 'HTTP Error 401: Unauthorized',
        last_latency_ms: 0,
        last_reason: 'schedule',
        consecutive_fail: 0,
        stale: false,
        enabled: true,
        next_check_at: '',
      },
      api_routes: [],
    } as unknown as LlmOpsData;
    expect(llmOpsHealthLabel(data).text).toBe('金鑰驗證失敗');
  });
});
