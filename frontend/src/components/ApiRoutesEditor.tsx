/**
 * API 分割編輯器：多供應商（千問／DeepSeek／Kimi／OpenRouter）+ 每組多模型。
 * 設定彈窗與控制台「API 路由」共用，避免兩套入口漂移。
 */
import { useCallback, useEffect, useId, useMemo, useState } from 'react';
import {
  deleteApiRoute,
  fetchConfig,
  refreshApiRoute,
  refreshLlmModels,
  testApiRoute,
  updateRouteStrategy,
  upsertApiRoute,
  type LlmConfig,
} from '../api/client';
import type { ApiRoutePublic } from '../types';
import { EDIT_API_ROUTE_EVENT, NEW_API_ROUTE_EVENT, dispatchApiRoutesChanged } from '../lib/agentUi';
import { navPathForTab } from '../lib/monitorTabs';

export const PROVIDER_PRESETS = [
  {
    value: 'qwen',
    label: '通義千問 Qwen',
    apiBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    defaultModel: 'qwen-plus',
    hint: '同一金鑰可勾選 qwen-plus / qwen-max / qwen-turbo 等多模型',
    models: ['qwen-plus', 'qwen-turbo', 'qwen-max', 'qwen-long', 'qwen3.5-max', 'qwen3-coder-plus'],
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    apiBase: 'https://api.deepseek.com',
    defaultModel: 'deepseek-v4-flash',
    hint: '單一廠商；可與千問、OpenRouter 同時存在',
    models: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-v4-flash-vision-exp'],
  },
  {
    value: 'moonshot',
    label: 'Moonshot / Kimi',
    apiBase: 'https://api.moonshot.cn/v1',
    defaultModel: 'kimi-k2',
    hint: 'Kimi 金鑰；可與其他 API 並行',
    models: ['kimi-k2', 'kimi-k3', 'moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
  },
  {
    value: 'openrouter',
    label: 'OpenRouter（通用目錄）',
    apiBase: 'https://openrouter.ai/api/v1',
    defaultModel: '',
    hint: '一個金鑰對應數百個模型；儲存後爬取 /models（已排除 Claude）',
    models: [] as string[],
  },
  {
    value: 'openai',
    label: 'OpenAI',
    apiBase: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o',
    hint: '官方端點',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini'],
  },
  {
    value: 'zhipu',
    label: '智譜 GLM',
    apiBase: 'https://open.bigmodel.cn/api/paas/v4',
    defaultModel: 'glm-4-flash',
    hint: '單一廠商金鑰',
    models: ['glm-4', 'glm-4-flash', 'glm-4-plus', 'glm-5.2'],
  },
  {
    value: 'ollama',
    label: 'Ollama（本地）',
    apiBase: 'http://127.0.0.1:11434/v1',
    defaultModel: '',
    hint: '儲存後爬取本機 /v1/models',
    models: [] as string[],
  },
  {
    value: 'custom',
    label: '自訂（OpenAI 相容）',
    apiBase: '',
    defaultModel: '',
    hint: 'vLLM / 閘道等相容端點',
    models: [] as string[],
  },
] as const;

export type ProviderValue = (typeof PROVIDER_PRESETS)[number]['value'];

const inputCls =
  'w-full rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2 text-sm text-[#F5F5F7] placeholder-[#636366] outline-none focus:border-[#007AFF]/60';

interface RouteDraft {
  id: string;
  name: string;
  provider: ProviderValue;
  apiKey: string;
  apiBase: string;
  model: string;
  weight: number;
  enabled: boolean;
  fallback: boolean;
  isDefault: boolean;
  allowedModels: string[];
  modelsLocked: boolean;
  orSort: '' | 'price' | 'latency';
  orOnly: string;
}

function emptyDraft(provider: ProviderValue = 'qwen'): RouteDraft {
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

interface ApiRoutesEditorProps {
  /** 儲存／刪除／測連後回呼（控制台同步健康快照、頂欄「未配置」） */
  onChanged?: () => void;
  className?: string;
  /** 設定彈窗用：隱藏「刷新全部目錄」（控制台已有） */
  compact?: boolean;
  /** 控制台側欄已有清單時隱藏重複列表 */
  hideList?: boolean;
}

export default function ApiRoutesEditor({ onChanged, className = '', compact = false, hideList = false }: ApiRoutesEditorProps) {
  const modelListId = useId();
  const [cfg, setCfg] = useState<LlmConfig | null>(null);
  const [draft, setDraft] = useState(emptyDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [status, setStatus] = useState<{ kind: 'idle' | 'busy' | 'ok' | 'fail'; text: string }>({
    kind: 'idle',
    text: '',
  });

  const routes = cfg?.api_routes ?? [];
  const strategies = cfg?.route_strategies ?? [
    { id: 'role_preferred', label: '角色指定優先' },
    { id: 'weighted_round_robin', label: '加權輪詢' },
    { id: 'random', label: '加權隨機' },
    { id: 'least_loaded', label: '最少負載' },
    { id: 'failover', label: '主備故障轉移' },
  ];

  const load = useCallback(async () => {
    const next = await fetchConfig();
    setCfg(next);
    return next;
  }, []);

  useEffect(() => {
    void load().catch(() => setCfg(null));
  }, [load]);

  const selectProvider = useCallback((value: ProviderValue) => {
    const preset = PROVIDER_PRESETS.find((p) => p.value === value);
    setDraft((prev) => ({
      ...prev,
      provider: value,
      name: prev.id ? prev.name : preset?.label || prev.name,
      apiBase: preset?.apiBase ?? prev.apiBase,
      model: preset?.defaultModel || prev.model,
      allowedModels: [...(preset?.models ?? [])],
      modelsLocked: false,
      orSort: value === 'openrouter' ? prev.orSort : '',
      orOnly: value === 'openrouter' ? prev.orOnly : '',
    }));
  }, []);

  const startEdit = useCallback((route: ApiRoutePublic) => {
    setEditingId(route.id);
    const routing = route.provider_routing || {};
    const sort = routing.sort === 'price' || routing.sort === 'latency' ? routing.sort : '';
    const only = Array.isArray(routing.only)
      ? (routing.only as unknown[]).map((x) => String(x)).filter(Boolean).join(', ')
      : '';
    setDraft({
      id: route.id,
      name: route.name,
      provider: (PROVIDER_PRESETS.some((p) => p.value === route.provider)
        ? route.provider
        : 'custom') as ProviderValue,
      apiKey: '',
      apiBase: route.api_base,
      model: route.model,
      weight: route.weight || 10,
      enabled: route.enabled,
      fallback: route.fallback,
      isDefault: route.is_default,
      allowedModels: [...(route.allowed_models || [])],
      modelsLocked: Boolean(route.models_locked),
      orSort: sort as '' | 'price' | 'latency',
      orOnly: only,
    });
  }, []);

  useEffect(() => {
    const onEdit = (e: Event) => {
      const id = (e as CustomEvent<string>).detail;
      const route = routes.find((r) => r.id === id);
      if (route) startEdit(route);
    };
    const onNew = () => {
      setEditingId(null);
      setDraft(emptyDraft());
      setShowKey(false);
    };
    window.addEventListener(EDIT_API_ROUTE_EVENT, onEdit);
    window.addEventListener(NEW_API_ROUTE_EVENT, onNew);
    return () => {
      window.removeEventListener(EDIT_API_ROUTE_EVENT, onEdit);
      window.removeEventListener(NEW_API_ROUTE_EVENT, onNew);
    };
  }, [routes, startEdit]);

  const handleSaveRoute = useCallback(async () => {
    setStatus({ kind: 'busy', text: '儲存並刷新該 API 模型目錄…' });
    try {
      const payload: Parameters<typeof upsertApiRoute>[0] = {
        id: draft.id || undefined,
        name: draft.name,
        provider: draft.provider,
        api_base: draft.apiBase,
        model: draft.model,
        weight: draft.weight,
        enabled: draft.enabled,
        fallback: draft.fallback,
        is_default: draft.isDefault || routes.length === 0,
        keep_api_key: !draft.apiKey.trim(),
        allowed_models: draft.allowedModels,
        models_locked: draft.modelsLocked,
      };
      if (draft.apiKey.trim()) payload.api_key = draft.apiKey.trim();
      if (draft.provider === 'openrouter' && (draft.orSort || draft.orOnly.trim())) {
        const routing: Record<string, unknown> = {};
        if (draft.orSort) routing.sort = draft.orSort;
        const only = draft.orOnly.split(',').map((s) => s.trim()).filter(Boolean);
        if (only.length) routing.only = only;
        payload.provider_routing = routing;
      }
      const state = await upsertApiRoute(payload);
      const next = await load();
      setCfg({ ...next, api_routes: state.api_routes, route_strategy: state.route_strategy });
      setStatus({
        kind: 'ok',
        text: `已儲存「${draft.name || draft.provider}」。角色可在「${navPathForTab('agents')} → 設定」指定此 API。`,
      });
      setDraft(emptyDraft());
      setEditingId(null);
      setShowKey(false);
      onChanged?.();
      dispatchApiRoutesChanged();
    } catch (err) {
      setStatus({ kind: 'fail', text: (err as Error).message });
    }
  }, [draft, load, onChanged, routes.length]);

  const handleDelete = useCallback(
    async (routeId: string) => {
      setStatus({ kind: 'busy', text: '刪除中…' });
      try {
        const state = await deleteApiRoute(routeId);
        const next = await load();
        setCfg({ ...next, api_routes: state.api_routes });
        if (editingId === routeId) {
          setEditingId(null);
          setDraft(emptyDraft());
        }
        setStatus({ kind: 'ok', text: '已刪除該 API' });
        onChanged?.();
        dispatchApiRoutesChanged();
      } catch (err) {
        setStatus({ kind: 'fail', text: (err as Error).message });
      }
    },
    [editingId, load, onChanged],
  );

  const handleTest = useCallback(async (routeId: string) => {
    setStatus({ kind: 'busy', text: '測試連線中…' });
    try {
      const result = await testApiRoute(routeId);
      if (result.ok) {
        setStatus({ kind: 'ok', text: `連線成功（${result.reply}）` });
      } else {
        setStatus({ kind: 'fail', text: `失敗：${result.error}` });
      }
    } catch (err) {
      setStatus({ kind: 'fail', text: (err as Error).message });
    }
  }, []);

  const handleRefresh = useCallback(
    async (routeId?: string) => {
      setStatus({ kind: 'busy', text: routeId ? `爬取 ${routeId} /models…` : '爬取全部目錄…' });
      try {
        if (routeId) {
          await refreshApiRoute(routeId);
        } else {
          await refreshLlmModels();
        }
        await load();
        setStatus({ kind: 'ok', text: '目錄已更新' });
        onChanged?.();
        dispatchApiRoutesChanged();
      } catch (err) {
        setStatus({ kind: 'fail', text: (err as Error).message });
      }
    },
    [load, onChanged],
  );

  const handleStrategy = useCallback(
    async (strategy: string) => {
      try {
        const state = await updateRouteStrategy(strategy, cfg?.default_route_id);
        setCfg((prev) =>
          prev ? { ...prev, route_strategy: state.route_strategy, api_routes: state.api_routes } : prev,
        );
        onChanged?.();
        dispatchApiRoutesChanged();
      } catch (err) {
        setStatus({ kind: 'fail', text: (err as Error).message });
      }
    },
    [cfg?.default_route_id, onChanged],
  );

  const preset = useMemo(() => PROVIDER_PRESETS.find((p) => p.value === draft.provider), [draft.provider]);
  const editingModels = useMemo(() => {
    const route = routes.find((r) => r.id === (editingId || draft.id));
    const catalogIds = (route?.catalog ?? []).map((m) => m.id);
    const seen = new Set<string>();
    const out: string[] = [];
    for (const id of [...(preset?.models ?? []), ...catalogIds, ...(route?.allowed_models ?? []), ...draft.allowedModels]) {
      if (!id || seen.has(id)) continue;
      seen.add(id);
      out.push(id);
    }
    return out;
  }, [draft.allowedModels, draft.id, editingId, preset, routes]);

  const toggleModel = useCallback(
    (id: string) => {
      setDraft((prev) => {
        const has = prev.allowedModels.includes(id);
        const next = has ? prev.allowedModels.filter((x) => x !== id) : [...prev.allowedModels, id];
        const all = editingModels.length > 0 && next.length >= editingModels.length;
        return {
          ...prev,
          allowedModels: next,
          modelsLocked: next.length > 0 && !all,
          model: next.includes(prev.model) ? prev.model : next[0] || prev.model,
        };
      });
    },
    [editingModels.length],
  );

  return (
    <div className={`space-y-4 ${className}`}>
      <div className={`grid grid-cols-1 gap-3 ${compact || hideList ? '' : 'md:grid-cols-2'}`}>
        <label className="block">
          <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-[#636366]">
            全域分發策略
          </span>
          <select
            className={inputCls}
            value={cfg?.route_strategy || 'role_preferred'}
            onChange={(e) => void handleStrategy(e.target.value)}
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        {!compact && !hideList && (
          <div className="flex items-end">
            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={status.kind === 'busy'}
              className="w-full rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[#F5F5F7] hover:bg-white/[0.04] disabled:opacity-50"
            >
              刷新全部模型目錄
            </button>
          </div>
        )}
      </div>

      {cfg?.lock_message && <p className="text-[11px] text-[#64D2FF]/90">{cfg.lock_message}</p>}

      {hideList ? (
        <p className="text-[11px] text-[#8E8E93]">
          左側清單點選編輯；此處新增或修改金鑰與可用模型。
        </p>
      ) : (
      <div className="space-y-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-[#636366]">已配置的 API</p>
        {routes.length === 0 ? (
          <p className="rounded-xl border border-dashed border-white/[0.08] px-3 py-6 text-center text-sm text-[#636366]">
            尚未加入 API。請在下方選擇供應商並填入金鑰。
          </p>
        ) : (
          routes.map((route) => (
            <div
              key={route.id}
              className={`rounded-xl border px-3 py-2 ${
                editingId === route.id
                  ? 'border-[#007AFF]/40 bg-[#007AFF]/10'
                  : 'border-white/[0.08] bg-white/[0.02]'
              }`}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm text-[#F5F5F7]">
                    {route.name}
                    {route.is_default ? <span className="ml-2 text-[10px] text-[#64D2FF]">預設</span> : null}
                    {!route.enabled ? <span className="ml-2 text-[10px] text-[#FF9F0A]">停用</span> : null}
                    {route.fallback ? <span className="ml-2 text-[10px] text-[#636366]">備援</span> : null}
                  </p>
                  <p className="text-[11px] text-[#8E8E93]">
                    {route.provider_label} · {route.model || '未指定預設模型'} · {route.allowed_models.length} 個模型
                    {route.configured ? ` · ${route.api_key}` : ' · 未設金鑰'}
                    {route.models_locked ? ' · 已鎖定模型清單' : ''}
                  </p>
                  {route.allowed_models.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {route.allowed_models.slice(0, 8).map((mid) => (
                        <span
                          key={mid}
                          className="rounded border border-white/[0.08] bg-[#1C1C1E] px-1.5 py-0.5 font-mono text-[10px] text-[#8E8E93]"
                        >
                          {mid}
                        </span>
                      ))}
                      {route.allowed_models.length > 8 ? (
                        <span className="text-[10px] text-[#636366]">+{route.allowed_models.length - 8}</span>
                      ) : null}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-1">
                  <button
                    type="button"
                    className="rounded-lg border border-white/[0.08] px-2 py-0.5 text-[11px] text-[#AEAEB2] hover:bg-white/[0.04]"
                    onClick={() => startEdit(route)}
                  >
                    編輯
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-white/[0.08] px-2 py-0.5 text-[11px] text-[#AEAEB2] hover:bg-white/[0.04]"
                    onClick={() => void handleRefresh(route.id)}
                  >
                    目錄
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-white/[0.08] px-2 py-0.5 text-[11px] text-[#AEAEB2] hover:bg-white/[0.04]"
                    onClick={() => void handleTest(route.id)}
                  >
                    測試
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-[#FF453A]/30 px-2 py-0.5 text-[11px] text-[#FF453A] hover:bg-[#FF453A]/10"
                    onClick={() => void handleDelete(route.id)}
                  >
                    刪除
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
      )}

      <div className="rounded-xl border border-white/[0.08] p-3">
        <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-[#636366]">
          {editingId ? `編輯 ${editingId}` : '新增 API'}
        </p>
        <label className="mb-1 block text-[11px] text-[#8E8E93]">供應商</label>
        <select
          value={draft.provider}
          onChange={(e) => selectProvider(e.target.value as ProviderValue)}
          className={`mb-3 ${inputCls}`}
        >
          {PROVIDER_PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        {preset && <p className="mb-3 text-[11px] text-[#636366]">{preset.hint}</p>}

        <label className="mb-1 block text-[11px] text-[#8E8E93]">顯示名稱</label>
        <input
          className={`mb-3 ${inputCls}`}
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          placeholder="例如：公司千問 / 備援 OpenRouter"
        />

        <label className="mb-1 block text-[11px] text-[#8E8E93]">API Key</label>
        <div className="mb-3 flex gap-2">
          <input
            type={showKey ? 'text' : 'password'}
            value={draft.apiKey}
            onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
            placeholder={editingId ? '留空保持原金鑰' : 'sk-...'}
            className={`flex-1 ${inputCls}`}
          />
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className="shrink-0 rounded-xl border border-white/[0.08] px-2.5 text-sm text-[#8E8E93] hover:bg-white/[0.04]"
          >
            {showKey ? '隱藏' : '顯示'}
          </button>
        </div>

        <label className="mb-1 block text-[11px] text-[#8E8E93]">API 端點</label>
        <input
          className={`mb-3 ${inputCls}`}
          value={draft.apiBase}
          onChange={(e) => setDraft({ ...draft, apiBase: e.target.value })}
          placeholder="https://..."
        />

        <label className="mb-1 block text-[11px] text-[#8E8E93]">此 API 預設模型</label>
        <input
          list={modelListId}
          className={`mb-3 ${inputCls}`}
          value={draft.model}
          onChange={(e) => setDraft({ ...draft, model: e.target.value })}
          placeholder={editingModels[0] || preset?.defaultModel || '模型 ID'}
        />
        <datalist id={modelListId}>
          {editingModels.map((id) => (
            <option key={id} value={id} />
          ))}
        </datalist>

        {editingModels.length > 0 && (
          <div className="mb-3">
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[11px] text-[#8E8E93]">此 API 可用模型（勾選後角色下拉只會出現這些）</span>
              <button
                type="button"
                className="text-[11px] text-[#64D2FF] hover:underline"
                onClick={() =>
                  setDraft((prev) => ({
                    ...prev,
                    allowedModels: [...editingModels],
                    modelsLocked: false,
                  }))
                }
              >
                全選
              </button>
            </div>
            <div className="max-h-36 overflow-y-auto rounded-xl border border-white/[0.08] bg-[#0D0D0F] p-2">
              <div className="flex flex-wrap gap-1.5">
                {editingModels.slice(0, 80).map((id) => {
                  const on = draft.allowedModels.includes(id);
                  return (
                    <label
                      key={id}
                      className={`cursor-pointer rounded-lg border px-1.5 py-0.5 font-mono text-[11px] ${
                        on
                          ? 'border-[#007AFF]/40 bg-[#007AFF]/10 text-[#64D2FF]'
                          : 'border-white/[0.06] text-[#636366]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="mr-1 align-middle"
                        checked={on}
                        onChange={() => toggleModel(id)}
                      />
                      {id}
                    </label>
                  );
                })}
              </div>
              {editingModels.length > 80 ? (
                <p className="mt-1 text-[10px] text-[#636366]">僅顯示前 80 個，儲存後可從目錄再勾選</p>
              ) : null}
            </div>
          </div>
        )}

        {draft.provider === 'openrouter' && (
          <div className="mb-3 space-y-3">
            <label className="block">
              <span className="mb-1 block text-[11px] text-[#8E8E93]">OpenRouter 排序（Provider Routing）</span>
              <select
                className={inputCls}
                value={draft.orSort}
                onChange={(e) => setDraft({ ...draft, orSort: e.target.value as '' | 'price' | 'latency' })}
              >
                <option value="">預設</option>
                <option value="price">依價格</option>
                <option value="latency">依延遲</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-[11px] text-[#8E8E93]">
                允許的底層供應商（only，逗號分隔；空白=不限制）
              </span>
              <input
                className={inputCls}
                value={draft.orOnly}
                onChange={(e) => setDraft({ ...draft, orOnly: e.target.value })}
                placeholder="例如 openai, google, deepseek"
              />
            </label>
          </div>
        )}

        <div className="mb-3 grid grid-cols-2 gap-2 md:grid-cols-4">
          <label className="text-[11px] text-[#8E8E93]">
            權重
            <input
              type="number"
              min={1}
              max={100}
              className={`mt-1 ${inputCls}`}
              value={draft.weight}
              onChange={(e) => setDraft({ ...draft, weight: Number(e.target.value) || 10 })}
            />
          </label>
          <label className="flex items-end gap-2 text-[12px] text-[#AEAEB2]">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            />
            啟用
          </label>
          <label className="flex items-end gap-2 text-[12px] text-[#AEAEB2]">
            <input
              type="checkbox"
              checked={draft.fallback}
              onChange={(e) => setDraft({ ...draft, fallback: e.target.checked })}
            />
            備援
          </label>
          <label className="flex items-end gap-2 text-[12px] text-[#AEAEB2]">
            <input
              type="checkbox"
              checked={draft.isDefault}
              onChange={(e) => setDraft({ ...draft, isDefault: e.target.checked })}
            />
            設為預設
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          {editingId && (
            <button
              type="button"
              onClick={() => {
                setEditingId(null);
                setDraft(emptyDraft());
              }}
              className="flex-1 rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[#F5F5F7] hover:bg-white/[0.04]"
            >
              取消編輯
            </button>
          )}
          {hideList && editingId && (
            <>
              <button
                type="button"
                onClick={() => void handleRefresh(editingId)}
                className="rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[#F5F5F7] hover:bg-white/[0.04]"
              >
                目錄
              </button>
              <button
                type="button"
                onClick={() => void handleTest(editingId)}
                className="rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[#F5F5F7] hover:bg-white/[0.04]"
              >
                測試
              </button>
              <button
                type="button"
                onClick={() => void handleDelete(editingId)}
                className="rounded-xl border border-[#FF453A]/30 px-3 py-2 text-sm text-[#FF453A] hover:bg-[#FF453A]/10"
              >
                刪除
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => void handleSaveRoute()}
            disabled={status.kind === 'busy'}
            className="flex-1 rounded-xl bg-[#007AFF] px-3 py-2 text-sm font-medium text-white hover:bg-[#0A84FF] disabled:opacity-50"
          >
            {editingId ? '更新此 API' : '加入 API'}
          </button>
        </div>
      </div>

      {status.text && (
        <p
          className={`text-xs ${
            status.kind === 'ok' ? 'text-[#30D158]' : status.kind === 'fail' ? 'text-[#FF453A]' : 'text-[#8E8E93]'
          }`}
        >
          {status.text}
        </p>
      )}
    </div>
  );
}
