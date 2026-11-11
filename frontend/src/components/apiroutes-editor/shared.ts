/**
 * API 路由編輯器共用樣式與草稿工具。
 */
import { isTokenPlanUrl } from '../../lib/llmCatalog';
import type { ApiRoutePublic } from '../../types';
import { PROVIDER_PRESETS, type ProviderValue } from './presets';
import type { RouteDraft } from './types';

export const inputCls =
  'w-full rounded-xl border border-white/[0.08] bg-[var(--console-card)] px-3 py-2 text-sm text-[var(--console-ink)] placeholder-[var(--console-sub)] outline-none focus:border-[color-mix(in_srgb,var(--console-accent)_60%,transparent)]';

export function resolveProvider(route: ApiRoutePublic): ProviderValue {
  if (isTokenPlanUrl(route.api_base) || isTokenPlanUrl(route.catalog_url)) {
    return 'token-plan';
  }
  const hit = PROVIDER_PRESETS.find((p) => p.value === route.provider);
  return (hit?.value ?? 'custom') as ProviderValue;
}

export function emptyDraft(provider: ProviderValue = 'qwen'): RouteDraft {
  const preset = PROVIDER_PRESETS.find((p) => p.value === provider) ?? PROVIDER_PRESETS[0];
  return {
    id: '',
    name: String(preset.label),
    provider,
    apiKey: '',
    apiBase: String(preset.apiBase),
    model: String(preset.defaultModel),
    weight: 10,
    enabled: true,
    fallback: false,
    isDefault: false,
    allowedModels: [...preset.models],
    modelsLocked: false,
    orSort: '',
    orOnly: '',
  };
}
