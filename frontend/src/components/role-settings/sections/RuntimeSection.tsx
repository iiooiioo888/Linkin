/**
 * 執行／合規 section：通知、上限與護欄。
 */
import { Field, inputCls } from '../fields';
import type { DraftUpdater, RoleSettingsDraft } from '../types';

interface RuntimeSectionProps {
  draft: RoleSettingsDraft;
  setDraft: DraftUpdater;
}

export default function RuntimeSection({ draft, setDraft }: RuntimeSectionProps) {
  return (
    <section id="rs-runtime" className="rs-sec">
      <div className="rs-sec-h">
        <h3 className="rs-sec-t">執行／合規</h3>
        <span className="rs-sec-hint">通知、上限與護欄</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <Field label="標籤" hint="逗號分隔">
          <input className={inputCls} value={draft.tagsText} onChange={(e) => setDraft({ ...draft, tagsText: e.target.value })} />
        </Field>
        <Field label="通知頻道">
          <input className={inputCls} placeholder="slack:#ops / email" value={draft.notify_channel} onChange={(e) => setDraft({ ...draft, notify_channel: e.target.value })} />
        </Field>
        <Field label="安靜時段" hint="例 22:00-08:00">
          <input className={inputCls} value={draft.quiet_hours} onChange={(e) => setDraft({ ...draft, quiet_hours: e.target.value })} />
        </Field>
        <Field label="心跳秒數" hint="0=關閉">
          <input type="number" min={0} className={inputCls} value={draft.heartbeat_sec} onChange={(e) => setDraft({ ...draft, heartbeat_sec: Number(e.target.value) || 0 })} />
        </Field>
        <Field label="每日工作項上限" hint="0=不限">
          <input type="number" min={0} className={inputCls} value={draft.max_daily_items} onChange={(e) => setDraft({ ...draft, max_daily_items: Number(e.target.value) || 0 })} />
        </Field>
        <div className="flex flex-wrap gap-3 md:col-span-2">
          {[
            ['on_call', '值班中', draft.on_call],
            ['require_human_approval', '人工核准後才執行', draft.require_human_approval],
            ['stream_enabled', '允許串流', draft.stream_enabled],
            ['cache_enabled', '語義快取', draft.cache_enabled],
            ['pii_redact', '個資遮蔽', draft.pii_redact],
            ['mainland_only', '僅國內模型', draft.mainland_only],
            ['allow_tool_use', '允許工具', draft.allow_tool_use],
            ['auto_escalate', '失敗自動升級', draft.auto_escalate],
          ].map(([key, label, checked]) => (
            <label key={String(key)} className="flex items-center gap-2 text-[12px] text-[var(--console-sub)]">
              <input
                type="checkbox"
                checked={Boolean(checked)}
                onChange={(e) => setDraft({ ...draft, [key as string]: e.target.checked })}
              />
              {label as string}
            </label>
          ))}
        </div>
      </div>
    </section>
  );
}
