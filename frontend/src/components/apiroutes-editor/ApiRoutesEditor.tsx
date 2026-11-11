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
} from '../../api/client';
import type { ApiRoutePublic } from '../../types';
import { EDIT_API_ROUTE_EVENT, NEW_API_ROUTE_EVENT, dispatchApiRoutesChanged } from '../../lib/agentUi';
import { navPathForTab } from '../../lib/monitorTabs';
import { RouteForm } from './RouteForm';
import { RouteList } from './RouteList';
import { StrategyBar } from './StrategyBar';
import { PROVIDER_PRESETS, type ProviderValue } from './presets';
import { emptyDraft, resolveProvider } from './shared';
import type { ApiRoutesEditorProps } from './types';

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
    const provider = resolveProvider(route);
    setDraft({
      id: route.id,
      name: route.name,
      provider,
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
      <p className="text-[11px] text-[var(--console-sub)]">金鑰、端點與模型勾選只保存在目前登入帳號。</p>
      <StrategyBar
        cfg={cfg}
        compact={compact}
        hideList={hideList}
        strategies={strategies}
        status={status}
        handleStrategy={handleStrategy}
        handleRefresh={handleRefresh}
      />

      {cfg?.lock_message && <p className="text-[11px] text-[color-mix(in_srgb,var(--console-accent)_90%,transparent)]">{cfg.lock_message}</p>}

      <RouteList
        hideList={hideList}
        routes={routes}
        editingId={editingId}
        startEdit={startEdit}
        handleRefresh={handleRefresh}
        handleTest={handleTest}
        handleDelete={handleDelete}
      />

      <RouteForm
        editingId={editingId}
        setEditingId={setEditingId}
        draft={draft}
        setDraft={setDraft}
        preset={preset}
        showKey={showKey}
        setShowKey={setShowKey}
        selectProvider={selectProvider}
        editingModels={editingModels}
        toggleModel={toggleModel}
        modelListId={modelListId}
        status={status}
        hideList={hideList}
        handleRefresh={handleRefresh}
        handleTest={handleTest}
        handleDelete={handleDelete}
        handleSaveRoute={handleSaveRoute}
      />

      {status.text && (
        <p
          className={`text-xs ${
            status.kind === 'ok' ? 'text-[var(--console-green)]' : status.kind === 'fail' ? 'text-[var(--console-danger)]' : 'text-[var(--console-sub)]'
          }`}
        >
          {status.text}
        </p>
      )}
    </div>
  );
}
