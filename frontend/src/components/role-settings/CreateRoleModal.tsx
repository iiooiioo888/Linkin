/**
 * 新增／複製自定義角色 modal。
 */
import { useState } from 'react';
import { TIER_LABEL, rateOptionLabel } from '../../lib/agentUi';
import { modelsForRoute } from '../../lib/llmCatalog';
import { SUNSET_BLOCK_MESSAGE, filterSelectableHubIds, isSunsetHubId } from '../../lib/sunsetHubIds';
import type { AgentCatalogMeta, RoleAgent, RolePreset } from '../../types';
import { inputCls, routeOptionLabel } from './fields';

interface CreateRoleModalProps {
  catalog: AgentCatalogMeta | undefined;
  agents: RoleAgent[];
  cloneFrom?: RoleAgent | null;
  onClose: () => void;
  onCreate: (payload: Record<string, unknown>) => Promise<void>;
}

export function CreateRoleModal({ catalog, agents, cloneFrom, onClose, onCreate }: CreateRoleModalProps) {
  const presets = catalog?.role_presets ?? [];
  const [id, setId] = useState(cloneFrom ? `copy_${cloneFrom.id}` : '');
  const [name, setName] = useState(cloneFrom ? `${cloneFrom.name}（副本）` : '');
  const [level, setLevel] = useState(cloneFrom?.level ?? 3);
  const [category, setCategory] = useState(cloneFrom?.category || 'management');
  const [prompt, setPrompt] = useState(cloneFrom?.system_prompt ?? '');
  const [responsibilities, setResponsibilities] = useState((cloneFrom?.responsibilities ?? []).join('\n'));
  const [reportingTo, setReportingTo] = useState(cloneFrom?.reporting_to ?? '');
  const [tier, setTier] = useState(cloneFrom?.default_tier || 'routine');
  const [description, setDescription] = useState(cloneFrom?.description ?? '');
  const [model, setModel] = useState(() => {
    const m = cloneFrom?.preferred_model ?? '';
    return isSunsetHubId(m) ? '' : m;
  });
  const [provider, setProvider] = useState(cloneFrom?.preferred_provider ?? '');
  const [maxOutput, setMaxOutput] = useState(cloneFrom?.max_output_tokens ?? 4096);
  const [contextWindow, setContextWindow] = useState(cloneFrom?.context_window ?? 0);
  const [budget, setBudget] = useState(cloneFrom?.daily_budget_usd ?? 0);
  const [cloudBudget, setCloudBudget] = useState(cloneFrom?.cloud_daily_budget_usd ?? 0);
  const [routing, setRouting] = useState(cloneFrom?.routing_strategy || 'quality_first');
  const [parallel, setParallel] = useState(cloneFrom?.max_parallel_work ?? 2);
  const [language, setLanguage] = useState(cloneFrom?.language || 'zh-TW');
  const [priority, setPriority] = useState(cloneFrom?.priority ?? 3);
  const [requireReview, setRequireReview] = useState(cloneFrom?.always_require_review === true);
  const [onCall, setOnCall] = useState(cloneFrom?.on_call === true);
  const [mainlandOnly, setMainlandOnly] = useState(cloneFrom?.mainland_only === true);
  const [humanApproval, setHumanApproval] = useState(cloneFrom?.require_human_approval === true);
  const [tags, setTags] = useState((cloneFrom?.tags ?? []).join(', '));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [presetId, setPresetId] = useState(cloneFrom?.id ?? '');

  const applyPreset = (preset: RolePreset) => {
    setPresetId(preset.id);
    setName(preset.name);
    setId(preset.id);
    setLevel(preset.level);
    setCategory(preset.category);
    setPrompt(preset.system_prompt);
    setResponsibilities((preset.responsibilities ?? []).join('\n'));
    setReportingTo(preset.reporting_to ?? '');
    setTier(preset.default_tier);
    setDescription(preset.hint ?? '');
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto apple-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">{cloneFrom ? `複製「${cloneFrom.name}」` : '新增自定義角色'}</h3>
          <button type="button" className="text-[12px] text-[var(--console-faint)]" onClick={onClose}>
            關閉
          </button>
        </div>
        {error && <p className="mb-2 text-[12px] text-red-300">{error}</p>}
        {presets.length > 0 && !cloneFrom && (
          <div className="mb-3">
            <p className="mb-1 text-[10px] text-[var(--console-faint)]">快速模板</p>
            <div className="flex flex-wrap gap-1">
              {presets.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  title={p.hint}
                  onClick={() => applyPreset(p)}
                  className={`rounded border px-2 py-1 text-[11px] ${
                    presetId === p.id
                      ? 'border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_15%,transparent)] text-[var(--console-accent)]'
                      : 'border-white/[0.08] text-[var(--console-faint)]'
                  }`}
                >
                  {p.name}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="space-y-2">
          <input className={inputCls} placeholder="顯示名稱（如 量化交易員）" value={name} onChange={(e) => setName(e.target.value)} />
          <input className={inputCls} placeholder="id 建議英文（自動加 custom_ 前綴）" value={id} onChange={(e) => setId(e.target.value)} />
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <select className={inputCls} value={level} onChange={(e) => setLevel(Number(e.target.value))}>
              {(catalog?.levels ?? []).map((lv) => (
                <option key={lv.level} value={lv.level}>
                  {lv.label}
                </option>
              ))}
            </select>
            <select className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
              {(catalog?.categories ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
            <select className={inputCls} value={tier} onChange={(e) => setTier(e.target.value)}>
              {(catalog?.tiers ?? Object.entries(TIER_LABEL).map(([tid, label]) => ({ id: tid, label }))).map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
            <select className={inputCls} value={reportingTo} onChange={(e) => setReportingTo(e.target.value)}>
              <option value="">無上級</option>
              {agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>
          <textarea
            className={inputCls}
            rows={5}
            placeholder="系統提示詞（角色設定）"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <textarea
            className={inputCls}
            rows={3}
            placeholder="職責，一行一項"
            value={responsibilities}
            onChange={(e) => setResponsibilities(e.target.value)}
          />
          <input
            className={inputCls}
            placeholder="一句話職責（目錄摘要）"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <select
              className={inputCls}
              value={provider}
              onChange={(e) => {
                const next = e.target.value;
                const routeModels = modelsForRoute(catalog?.models_by_provider ?? [], next);
                setProvider(next);
                if (next && routeModels.length > 0 && !routeModels.includes(model)) {
                  setModel(routeModels[0] || '');
                }
              }}
            >
              <option value="">API：全域預設</option>
              {(catalog?.api_routes ?? []).map((route) => (
                <option key={route.id} value={route.id}>
                  {routeOptionLabel(route)}
                </option>
              ))}
            </select>
            <select className={inputCls} value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">模型：該 API 預設</option>
              {(catalog?.models_by_provider ?? [])
                .filter((g) => !provider || g.route_id === provider)
                .flatMap((g) =>
                  filterSelectableHubIds(g.models).map((mid) => ({ group: g.name, mid })),
                )
                .map((row) => (
                  <option key={`${row.group}-${row.mid}`} value={row.mid}>
                    {rateOptionLabel(row.mid, catalog?.model_rate_cards)}
                  </option>
                ))}
            </select>
            <input
              className={inputCls}
              type="number"
              min={256}
              max={128000}
              placeholder="輸出 Token"
              value={maxOutput}
              onChange={(e) => setMaxOutput(Number(e.target.value) || 4096)}
            />
            <input
              className={inputCls}
              type="number"
              min={0}
              max={2000000}
              placeholder="上下文 Token（0=不截斷）"
              value={contextWindow}
              onChange={(e) => setContextWindow(Number(e.target.value) || 0)}
            />
            <select className={inputCls} value={routing} onChange={(e) => setRouting(e.target.value)}>
              {(catalog?.routing_strategies ?? [{ id: 'quality_first', label: '品質優先' }]).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
            <input
              className={inputCls}
              type="number"
              min={0}
              step={0.1}
              placeholder="AI 日預算 USD"
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value) || 0)}
            />
            <input
              className={inputCls}
              type="number"
              min={0}
              step={0.1}
              placeholder="雲服務日預算 USD"
              value={cloudBudget}
              onChange={(e) => setCloudBudget(Number(e.target.value) || 0)}
            />
            <input
              className={inputCls}
              type="number"
              min={1}
              max={16}
              placeholder="並行"
              value={parallel}
              onChange={(e) => setParallel(Number(e.target.value) || 2)}
            />
            <select className={inputCls} value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="zh-TW">繁中</option>
              <option value="zh-CN">簡中</option>
              <option value="en">English</option>
            </select>
            <input
              className={inputCls}
              type="number"
              min={1}
              max={5}
              placeholder="優先級"
              value={priority}
              onChange={(e) => setPriority(Number(e.target.value) || 3)}
            />
            <label className="flex items-center gap-2 text-[11px] text-[var(--console-sub)]">
              <input type="checkbox" checked={requireReview} onChange={(e) => setRequireReview(e.target.checked)} />
              一律送審查
            </label>
            <label className="flex items-center gap-2 text-[11px] text-[var(--console-sub)]">
              <input type="checkbox" checked={onCall} onChange={(e) => setOnCall(e.target.checked)} />
              值班
            </label>
            <label className="flex items-center gap-2 text-[11px] text-[var(--console-sub)]">
              <input type="checkbox" checked={humanApproval} onChange={(e) => setHumanApproval(e.target.checked)} />
              需人工核准
            </label>
            <label className="flex items-center gap-2 text-[11px] text-[var(--console-sub)]">
              <input type="checkbox" checked={mainlandOnly} onChange={(e) => setMainlandOnly(e.target.checked)} />
              僅國內模型
            </label>
          </div>
          <input className={inputCls} placeholder="標籤，逗號分隔" value={tags} onChange={(e) => setTags(e.target.value)} />
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className="rounded border border-white/[0.08] px-3 py-1.5 text-[12px] text-[var(--console-faint)]" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            disabled={busy || !name.trim()}
            className="rounded border border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_15%,transparent)] px-3 py-1.5 text-[12px] text-[var(--console-accent)] disabled:opacity-40"
            onClick={async () => {
              setBusy(true);
              setError(null);
              try {
                if (isSunsetHubId(model)) {
                  throw new Error(SUNSET_BLOCK_MESSAGE);
                }
                await onCreate({
                  id: id.trim() || name.trim(),
                  name: name.trim(),
                  level,
                  category,
                  default_tier: tier,
                  system_prompt: prompt,
                  responsibilities: responsibilities.split('\n').map((s) => s.trim()).filter(Boolean),
                  reporting_to: reportingTo || agents.find((a) => a.level < level)?.id || 'manager',
                  clone_from: cloneFrom?.id,
                  description,
                  preferred_model: model,
                  preferred_provider: provider,
                  max_output_tokens: maxOutput,
                  context_window: contextWindow,
                  daily_budget_usd: budget,
                  weekly_budget_usd: cloneFrom?.weekly_budget_usd ?? 0,
                  monthly_budget_usd: cloneFrom?.monthly_budget_usd ?? 0,
                  cloud_daily_budget_usd: cloudBudget,
                  cloud_weekly_budget_usd: cloneFrom?.cloud_weekly_budget_usd ?? 0,
                  cloud_monthly_budget_usd: cloneFrom?.cloud_monthly_budget_usd ?? 0,
                  routing_strategy: routing,
                  max_parallel_work: parallel,
                  language,
                  priority,
                  always_require_review: requireReview,
                  on_call: onCall,
                  require_human_approval: humanApproval,
                  mainland_only: mainlandOnly,
                  tags: tags.split(',').map((s) => s.trim()).filter(Boolean),
                });
                onClose();
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? '建立中…' : cloneFrom ? '建立副本' : '建立'}
          </button>
        </div>
      </div>
    </div>
  );
}
