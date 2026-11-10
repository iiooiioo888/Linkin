/**
 * 身分／組織 section：名稱、啟用、職級、匯報與指派。
 */
import { CATEGORY_LABEL } from '../../../lib/agentUi';
import { agentRahoLabel } from '../../../lib/rahoUi';
import type { AgentCatalogMeta, RoleAgent } from '../../../types';
import { Field, inputCls } from '../fields';
import type { DraftUpdater, RoleSettingsDraft } from '../types';

interface IdentitySectionProps {
  agent: RoleAgent;
  agents: RoleAgent[];
  catalog: AgentCatalogMeta | undefined;
  draft: RoleSettingsDraft;
  setDraft: DraftUpdater;
}

export default function IdentitySection({ agent, agents, catalog, draft, setDraft }: IdentitySectionProps) {
  const categories = catalog?.categories ?? Object.entries(CATEGORY_LABEL).map(([id, label]) => ({ id, label }));
  const levels = catalog?.levels ?? [];
  const tools = catalog?.tool_names ?? [];

  return (
    <section id="rs-identity" className="rs-sec">
      <div className="rs-sec-h">
        <h3 className="rs-sec-t">身分／組織</h3>
        <span className="rs-sec-hint">組織職級是公司匯報鏈</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <Field label="顯示名稱">
          <input className={inputCls} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </Field>
        <Field label="啟用">
          <button
            type="button"
            onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
            className={`rounded-md border px-3 py-1.5 text-[12px] ${
              draft.enabled
                ? 'border-[color-mix(in_srgb,var(--console-green)_40%,transparent)] bg-[color-mix(in_srgb,var(--console-green)_10%,transparent)] text-[var(--console-green)]'
                : 'border-red-500/30 bg-red-500/10 text-red-300'
            }`}
          >
            {draft.enabled ? '已啟用 · 可被指派' : '已停用 · 分解時排除'}
          </button>
        </Field>
        <Field label="顯示層">
          <input className={inputCls} value={agentRahoLabel(agent)} readOnly />
        </Field>
        <Field label="組織職級">
          <select
            className={inputCls}
            value={draft.level}
            onChange={(e) => setDraft({ ...draft, level: Number(e.target.value) })}
          >
            {levels.map((lv) => (
              <option key={lv.level} value={lv.level}>
                {lv.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="分類">
          <select
            className={inputCls}
            value={draft.category}
            onChange={(e) => setDraft({ ...draft, category: e.target.value })}
          >
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="匯報對象">
          <select
            className={inputCls}
            value={draft.reporting_to}
            onChange={(e) => setDraft({ ...draft, reporting_to: e.target.value })}
          >
            <option value="">無上級</option>
            {agents
              .filter((a) => a.id !== agent.id)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
          </select>
        </Field>
        <Field label="可委派" hint="逗號分隔 id">
          <input
            className={inputCls}
            value={draft.can_delegate_to}
            onChange={(e) => setDraft({ ...draft, can_delegate_to: e.target.value })}
          />
        </Field>
        <Field label="並行上限">
          <input
            type="number"
            min={1}
            max={16}
            className={inputCls}
            value={draft.max_parallel_work}
            onChange={(e) => setDraft({ ...draft, max_parallel_work: Number(e.target.value) || 1 })}
          />
        </Field>
        <Field label="優先級" hint="1=最高 5=最低">
          <input
            type="number"
            min={1}
            max={5}
            className={inputCls}
            value={draft.priority}
            onChange={(e) => setDraft({ ...draft, priority: Number(e.target.value) || 3 })}
          />
        </Field>
        <Field label="輸出語言">
          <select
            className={inputCls}
            value={draft.language}
            onChange={(e) => setDraft({ ...draft, language: e.target.value })}
          >
            <option value="zh-TW">繁體中文</option>
            <option value="zh-CN">簡體中文</option>
            <option value="en">English</option>
          </select>
        </Field>
        <Field label="允許工具" hint={tools.length ? tools.join(' · ') : '逗號分隔'}>
          <input
            className={inputCls}
            value={draft.toolsText}
            onChange={(e) => setDraft({ ...draft, toolsText: e.target.value })}
          />
        </Field>
        <Field label="一句話職責" hint="目錄卡片摘要">
          <input
            className={inputCls}
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />
        </Field>
      </div>
    </section>
  );
}
