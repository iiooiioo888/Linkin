/**
 * 角色設定主面板：toolbar、分區導覽與五個 section 的組裝。
 */
import { useEffect, useMemo, useState } from 'react';
import AlertsSection from './sections/AlertsSection';
import IdentitySection from './sections/IdentitySection';
import ModelSection from './sections/ModelSection';
import PromptSection from './sections/PromptSection';
import RuntimeSection from './sections/RuntimeSection';
import { SETTINGS_SECTIONS, draftFromAgent } from './types';
import type { RoleSettingsDraft, RoleSettingsPanelProps, RoleSettingsSection } from './types';

export default function RoleSettingsPanel({
  agent,
  catalog,
  agents,
  saving,
  error,
  initialSection = 'identity',
  onSave,
  onReset,
  onDelete,
  onClone,
  onCreate,
}: RoleSettingsPanelProps) {
  const [draft, setDraft] = useState<RoleSettingsDraft>(() => draftFromAgent(agent));
  const [section, setSection] = useState<RoleSettingsSection>(initialSection);

  useEffect(() => {
    setDraft(draftFromAgent(agent));
  }, [agent]);

  useEffect(() => {
    setSection(initialSection);
  }, [agent.id, initialSection]);

  const goSection = (id: RoleSettingsSection) => {
    setSection(id);
    document.getElementById(`rs-${id}`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  };

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(draftFromAgent(agent)), [agent, draft]);

  return (
    <div className="rs-wrap">
      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-[12px] text-red-200">{error}</p>
      )}
      <div className="rs-toolbar">
        <div className="rs-head">
          <div className="rs-head-l">
            <h2 className="rs-title">角色設定</h2>
            <p className="rs-sub">
              {agent.is_custom
                ? '自定義角色，可刪除'
                : '內建角色 · 可覆蓋設定，還原後回到內建預設'}
            </p>
          </div>
          <div className="rs-actions">
            {onCreate && (
              <button type="button" onClick={onCreate} className="rs-act">
                新增角色
              </button>
            )}
            {onClone && (
              <button type="button" onClick={() => onClone(agent)} className="rs-act">
                複製為自定義
              </button>
            )}
            {onReset && !agent.is_custom && (
              <button type="button" onClick={() => void onReset()} className="rs-act">
                還原預設
              </button>
            )}
            {onDelete && agent.is_custom && (
              <button type="button" onClick={() => void onDelete()} className="rs-act rs-act--danger">
                刪除角色
              </button>
            )}
            <button
              type="button"
              disabled={saving || !dirty}
              onClick={() => void onSave(draft)}
              className="rs-act rs-act--primary"
            >
              {saving ? '儲存中…' : '儲存設定'}
            </button>
          </div>
        </div>
      </div>

      <div className="rs-body">
        <nav className="sp-nav rs-nav" aria-label="角色設定分區">
          <div className="sp-group">設定</div>
          <div className="sp-list">
            {SETTINGS_SECTIONS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`sp-item ${section === item.id ? 'on' : ''}`}
                onClick={() => goSection(item.id)}
              >
                <span className="sp-item-ic">{item.icon}</span>
                <span className="sp-item-txt">
                  <span className="sp-item-l">{item.label}</span>
                  <span className="sp-item-h">{item.hint}</span>
                </span>
              </button>
            ))}
          </div>
        </nav>
        <div className="min-w-0 space-y-3.5">
          <IdentitySection agent={agent} agents={agents} catalog={catalog} draft={draft} setDraft={setDraft} />
          <ModelSection catalog={catalog} draft={draft} setDraft={setDraft} />
          <PromptSection draft={draft} setDraft={setDraft} />
          <RuntimeSection draft={draft} setDraft={setDraft} />
          <AlertsSection agent={agent} draft={draft} setDraft={setDraft} />
        </div>
      </div>
    </div>
  );
}
