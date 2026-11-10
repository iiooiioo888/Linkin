/**
 * 提示詞／職責 section：系統提示詞、職責清單與備註。
 */
import PromptEditor from '../../PromptEditor';
import { Field, inputCls } from '../fields';
import type { DraftUpdater, RoleSettingsDraft } from '../types';

interface PromptSectionProps {
  draft: RoleSettingsDraft;
  setDraft: DraftUpdater;
}

export default function PromptSection({ draft, setDraft }: PromptSectionProps) {
  return (
    <section id="rs-prompt" className="rs-sec">
      <div className="rs-sec-h">
        <h3 className="rs-sec-t">提示詞／職責</h3>
        <span className="rs-sec-hint">系統提示詞與職責清單</span>
      </div>
      <div className="space-y-3">
        <Field label="系統提示詞" hint="Monaco · 語法高亮">
          <PromptEditor
            value={draft.system_prompt}
            onChange={(v) => setDraft({ ...draft, system_prompt: v })}
            height={280}
          />
        </Field>
        <Field label="職責" hint="一行一項">
          <textarea
            rows={6}
            className={inputCls}
            value={draft.responsibilitiesText}
            onChange={(e) => setDraft({ ...draft, responsibilitiesText: e.target.value })}
          />
        </Field>
        <Field label="備註">
          <textarea
            rows={2}
            className={inputCls}
            value={draft.notes}
            onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
          />
        </Field>
      </div>
    </section>
  );
}
