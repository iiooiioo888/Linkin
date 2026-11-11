/**
 * API 路由編輯器：新增／編輯表單（供應商、金鑰、端點、模型勾選、旗標）。
 */
import type { Dispatch, SetStateAction } from 'react';
import { isTokenPlanUrl, TOKEN_PLAN_LABEL } from '../../lib/llmCatalog';
import { PROVIDER_PRESETS, type ProviderValue } from './presets';
import { emptyDraft, inputCls } from './shared';
import type { EditorStatus, RouteDraft } from './types';

interface RouteFormProps {
  editingId: string | null;
  setEditingId: Dispatch<SetStateAction<string | null>>;
  draft: RouteDraft;
  setDraft: Dispatch<SetStateAction<RouteDraft>>;
  preset: (typeof PROVIDER_PRESETS)[number] | undefined;
  showKey: boolean;
  setShowKey: Dispatch<SetStateAction<boolean>>;
  selectProvider: (value: ProviderValue) => void;
  editingModels: string[];
  toggleModel: (id: string) => void;
  modelListId: string;
  status: EditorStatus;
  hideList: boolean;
  handleRefresh: (routeId?: string) => Promise<void>;
  handleTest: (routeId: string) => Promise<void>;
  handleDelete: (routeId: string) => Promise<void>;
  handleSaveRoute: () => Promise<void>;
}

export function RouteForm({
  editingId,
  setEditingId,
  draft,
  setDraft,
  preset,
  showKey,
  setShowKey,
  selectProvider,
  editingModels,
  toggleModel,
  modelListId,
  status,
  hideList,
  handleRefresh,
  handleTest,
  handleDelete,
  handleSaveRoute,
}: RouteFormProps) {
  return (
    <div className="rounded-xl border border-white/[0.08] p-3">
      <p className="mb-3 text-[10px] font-semibold text-[var(--console-sub)]">
        {editingId ? `編輯 ${editingId}` : '新增 API'}
      </p>
      <label className="mb-1 block text-[11px] text-[var(--console-sub)]">供應商</label>
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
      {preset && <p className="mb-3 text-[11px] text-[var(--console-sub)]">{preset.hint}</p>}

      <label className="mb-1 block text-[11px] text-[var(--console-sub)]">顯示名稱</label>
      <input
        className={`mb-3 ${inputCls}`}
        value={draft.name}
        onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        placeholder="例如：公司千問 / 備援 OpenRouter"
      />

      <label className="mb-1 block text-[11px] text-[var(--console-sub)]">API Key</label>
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
          className="shrink-0 rounded-xl border border-white/[0.08] px-2.5 text-sm text-[var(--console-sub)] hover:bg-white/[0.04]"
        >
          {showKey ? '隱藏' : '顯示'}
        </button>
      </div>

      <label className="mb-1 block text-[11px] text-[var(--console-sub)]">API 端點</label>
      <input
        className={`mb-3 ${inputCls}`}
        value={draft.apiBase}
        onChange={(e) => {
          const apiBase = e.target.value;
          const next: Partial<RouteDraft> = { apiBase };
          if (isTokenPlanUrl(apiBase) && draft.provider !== 'token-plan') {
            const preset = PROVIDER_PRESETS.find((p) => p.value === 'token-plan');
            next.provider = 'token-plan';
            if (!draft.id && (!draft.name || draft.name === PROVIDER_PRESETS[1]?.label)) {
              next.name = preset?.label || TOKEN_PLAN_LABEL;
            }
          }
          setDraft((prev) => ({ ...prev, ...next }));
        }}
        placeholder="https://..."
      />

      <label className="mb-1 block text-[11px] text-[var(--console-sub)]">此 API 預設模型</label>
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
            <span className="text-[11px] text-[var(--console-sub)]">此 API 可用模型（勾選後角色下拉只會出現這些）</span>
            <button
              type="button"
              className="text-[11px] text-[var(--console-accent)] hover:underline"
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
          <div className="max-h-36 overflow-y-auto rounded-xl border border-white/[0.08] bg-[var(--console-bg)] p-2">
            <div className="flex flex-wrap gap-1.5">
              {editingModels.slice(0, 80).map((id) => {
                const on = draft.allowedModels.includes(id);
                return (
                  <label
                    key={id}
                    className={`cursor-pointer rounded-lg border px-1.5 py-0.5 font-mono text-[11px] ${
                      on
                        ? 'border-[color-mix(in_srgb,var(--console-accent)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-accent)_10%,transparent)] text-[var(--console-accent)]'
                        : 'border-white/[0.06] text-[var(--console-sub)]'
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
              <p className="mt-1 text-[10px] text-[var(--console-sub)]">僅顯示前 80 個，儲存後可從目錄再勾選</p>
            ) : null}
          </div>
        </div>
      )}

      {draft.provider === 'openrouter' && (
        <div className="mb-3 space-y-3">
          <label className="block">
            <span className="mb-1 block text-[11px] text-[var(--console-sub)]">OpenRouter 排序（Provider Routing）</span>
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
            <span className="mb-1 block text-[11px] text-[var(--console-sub)]">
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
        <label className="text-[11px] text-[var(--console-sub)]">
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
        <label className="flex items-end gap-2 text-[12px] text-[var(--console-sub)]">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
          />
          啟用
        </label>
        <label className="flex items-end gap-2 text-[12px] text-[var(--console-sub)]">
          <input
            type="checkbox"
            checked={draft.fallback}
            onChange={(e) => setDraft({ ...draft, fallback: e.target.checked })}
          />
          備援
        </label>
        <label className="flex items-end gap-2 text-[12px] text-[var(--console-sub)]">
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
            className="flex-1 rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[var(--console-ink)] hover:bg-white/[0.04]"
          >
            取消編輯
          </button>
        )}
        {hideList && editingId && (
          <>
            <button
              type="button"
              onClick={() => void handleRefresh(editingId)}
              className="rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[var(--console-ink)] hover:bg-white/[0.04]"
            >
              目錄
            </button>
            <button
              type="button"
              onClick={() => void handleTest(editingId)}
              className="rounded-xl border border-white/[0.08] px-3 py-2 text-sm text-[var(--console-ink)] hover:bg-white/[0.04]"
            >
              測試
            </button>
            <button
              type="button"
              onClick={() => void handleDelete(editingId)}
              className="rounded-xl border border-[color-mix(in_srgb,var(--console-danger)_30%,transparent)] px-3 py-2 text-sm text-[var(--console-danger)] hover:bg-[color-mix(in_srgb,var(--console-danger)_10%,transparent)]"
            >
              刪除
            </button>
          </>
        )}
        <button
          type="button"
          onClick={() => void handleSaveRoute()}
          disabled={status.kind === 'busy'}
          className="flex-1 rounded-xl bg-[var(--console-accent)] px-3 py-2 text-sm font-medium text-white hover:bg-[var(--console-accent)] disabled:opacity-50"
        >
          {editingId ? '更新此 API' : '加入 API'}
        </button>
      </div>
    </div>
  );
}
