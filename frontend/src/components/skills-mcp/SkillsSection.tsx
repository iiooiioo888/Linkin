/**
 * 技能庫分頁：技能卡片、分級收合、新增／編輯表單、注入預覽與 Agent 包同步。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  deleteSkill,
  fetchSkills,
  openTokenDashboard,
  previewSkillPrompt,
  saveSkill,
  syncAgentSkillPacks,
  toggleSkill,
  type SkillRecord,
} from '../../api/client';
import { takeSkillFocus } from '../../lib/appRoute';
import MediaCrawlerPanel from '../MediaCrawlerPanel';
import { consoleLayout } from '../ui/ConsoleLayout';
import { CliRuntimeStrip } from './CliSection';
import { ErrorBar, OkBar, TierSection } from './shared';
import { btnCls, btnPrimaryCls, cardCls, inputCls } from './styles';
import { skillTierOf } from './tiers';

const SKILL_TYPE_LABELS: Record<string, string> = {
  'agent-pack': 'Agent 包',
  'cli-stub': '需 CLI',
  'cursor-only': 'Cursor 專用',
  custom: '自訂',
};

function SkillTypeBadge({ skill }: { skill: SkillRecord }) {
  const type = skill.skill_type || 'custom';
  const label = SKILL_TYPE_LABELS[type] || type;
  const tone =
    type === 'cursor-only'
      ? 'bg-amber-500/15 text-amber-300'
      : type === 'cli-stub'
        ? 'bg-sky-500/15 text-sky-300'
        : type === 'agent-pack'
          ? 'bg-violet-500/15 text-violet-300'
          : 'bg-white/[0.06] text-[var(--console-faint)]';
  return (
    <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${tone}`} title={skill.source_path || undefined}>
      {label}
    </span>
  );
}

// ══════════════ 技能庫 ══════════════

const EMPTY_SKILL_FORM = {
  id: '' as string,
  name: '',
  description: '',
  trigger: '',
  content: '',
  roles: '',
  enabled: true,
  skill_budget: 2400,
};

function skillSourceHref(source: string | undefined): string | null {
  if (!source || !/^[\w.-]+\/[\w.-]+$/.test(source)) return null;
  return `https://github.com/${source}`;
}

export function SkillsSection() {
  const { t } = useTranslation();
  const [skills, setSkills] = useState<SkillRecord[]>([]);
  const [form, setForm] = useState({ ...EMPTY_SKILL_FORM });
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [focusId] = useState<string | null>(() => takeSkillFocus());

  const load = useCallback(async () => {
    setError(null);
    try {
      setSkills(await fetchSkills());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!focusId || skills.length === 0) return;
    const catalog = focusId === 'cli-anything' ? document.getElementById('cli-anything-catalog') : null;
    (catalog ?? document.getElementById(`skill-card-${focusId}`))?.scrollIntoView({ block: 'start' });
  }, [focusId, skills]);

  const startEdit = (s: SkillRecord) => {
    setEditing(true);
    setForm({
      id: s.id,
      name: s.name,
      description: s.description,
      trigger: s.trigger,
      content: s.content,
      roles: s.roles.join(', '),
      enabled: s.enabled,
      skill_budget: s.skill_budget,
    });
  };

  const resetForm = () => {
    setEditing(false);
    setForm({ ...EMPTY_SKILL_FORM });
  };

  const onSave = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await saveSkill({
        id: form.id || null,
        name: form.name,
        content: form.content,
        description: form.description,
        trigger: form.trigger,
        roles: form.roles.split(',').map((r) => r.trim()).filter(Boolean),
        enabled: form.enabled,
        skill_budget: Number(form.skill_budget) || 2400,
      });
      setMessage(`已保存技能「${saved.name}」`);
      resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onToggle = async (s: SkillRecord) => {
    setError(null);
    try {
      await toggleSkill(s.id);
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onDelete = async (s: SkillRecord) => {
    setError(null);
    try {
      await deleteSkill(s.id);
      setMessage(`已刪除「${s.name}」`);
      if (form.id === s.id) resetForm();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onPreview = async () => {
    setError(null);
    try {
      const data = await previewSkillPrompt();
      setPreview(data.prompt || '（目前無啟用技能，注入區塊為空）');
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const onSyncAgentPacks = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const report = await syncAgentSkillPacks();
      const s = report.skills;
      setMessage(
        `已同步 Agent 技能包：新增 ${s.created}、更新 ${s.updated}、未變 ${s.unchanged}（目錄共 ${s.total_catalog} 條）；MCP 範本 +${report.mcp.created} ~${report.mcp.updated}`,
      );
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const managedCount = skills.filter((s) => s.managed).length;
  const tiers = useMemo(() => ({
    enabled: skills.filter((s) => skillTierOf(s) === 'enabled'),
    available: skills.filter((s) => skillTierOf(s) === 'available'),
    needsKey: skills.filter((s) => skillTierOf(s) === 'needsKey'),
  }), [skills]);

  const renderSkillCard = (s: SkillRecord) => (
    <div
      key={s.id}
      id={`skill-card-${s.id}`}
      className={`${cardCls} ${s.enabled ? '' : 'opacity-50'} ${
        focusId === s.id ? 'ring-1 ring-[color-mix(in_srgb,var(--console-accent)_55%,transparent)]' : ''
      }`}
    >
      <div className="mb-1 flex items-start justify-between gap-2">
        <div>
          <p className="text-[13px] font-medium text-[var(--console-ink)]">{s.name}</p>
          <p className="font-mono text-[10px] text-[var(--console-faint)]">{s.id}</p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1">
          <SkillTypeBadge skill={s} />
          <span className={`rounded px-1.5 py-0.5 text-[9px] font-semibold ${s.enabled ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/[0.06] text-[var(--console-faint)]'}`}>
            {s.enabled ? t('skills.tierEnabled') : t('skills.tierAvailable')}
          </span>
        </div>
      </div>
      {s.source && (
        <p className="mb-1 text-[10px] text-[var(--console-faint)]">
          來源：
          {skillSourceHref(s.source) ? (
            <a
              href={skillSourceHref(s.source) ?? undefined}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--console-accent)] hover:underline"
            >
              {s.source}
            </a>
          ) : (
            s.source
          )}
        </p>
      )}
      {s.description && <p className="mb-1 text-[11px] text-[var(--console-sub)]">{s.description}</p>}
      {s.trigger && <p className="mb-1 text-[10px] console-status-blue/80">適用：{s.trigger}</p>}
      <pre className="mb-2 max-h-24 overflow-auto whitespace-pre-wrap rounded-lg bg-black/30 p-2 font-mono text-[10px] leading-relaxed text-[var(--console-sub)]">{s.content}</pre>
      <p className="mb-2 text-[10px] text-[var(--console-faint)]">
        角色：{s.roles.length ? s.roles.join(', ') : '全部'} · 上限 {s.skill_budget} 字 · 更新 {s.updated_at ? s.updated_at.slice(0, 16).replace('T', ' ') : '—'}
      </p>
      <div className="flex gap-2">
        <button type="button" className={btnCls} onClick={() => startEdit(s)}>編輯</button>
        <button type="button" className={btnCls} onClick={() => void onToggle(s)}>{s.enabled ? '停用' : '啟用'}</button>
        <button type="button" className={`${btnCls} text-red-400/80 hover:console-status-danger`} onClick={() => void onDelete(s)}>刪除</button>
      </div>
    </div>
  );

  return (
    <div>
      <MediaCrawlerPanel />
      <CliRuntimeStrip />
      <ErrorBar message={error} />
      <OkBar message={message} />

      <div className="mb-4 flex items-center justify-between">
        <p className="text-[11px] text-[var(--console-sub)]">
          技能會注入角色的系統提示詞（參考資料區塊）；停用即不注入。共 {skills.length} 條，啟用 {skills.filter((s) => s.enabled).length} 條
          {managedCount > 0 ? `（含 ${managedCount} 條來自 .agents/skills/）` : ''}。
        </p>
        <div className="flex gap-2">
          <button type="button" className={btnCls} disabled={busy} onClick={() => void onSyncAgentPacks()} title="從 .agents/skills/ 匯入／更新">
            同步 Agent 包
          </button>
          <button type="button" className={btnCls} onClick={() => openTokenDashboard(30)} title="Linkin 計費庫 Token 用量看板">
            打開 Token 看板
          </button>
          <button type="button" className={btnCls} onClick={() => void onPreview()}>預覽注入區塊</button>
          <button type="button" className={btnCls} onClick={() => void load()}>重新整理</button>
          {!editing && (
            <button type="button" className={btnPrimaryCls} onClick={() => { resetForm(); setEditing(true); }}>＋ 新技能</button>
          )}
        </div>
      </div>

      {preview !== null && (
        <div className="mb-4">
          <pre className="max-h-48 overflow-auto rounded-xl border border-white/[0.08] bg-black/40 p-3 font-mono text-[11px] leading-relaxed text-[var(--console-sub)]">{preview}</pre>
          <button type="button" className={`${btnCls} mt-1`} onClick={() => setPreview(null)}>收起預覽</button>
        </div>
      )}

      {editing && (
        <section className={`${cardCls} mb-4`}>
          <h3 className="mb-2 text-[11px] font-semibold text-[var(--console-sub)]">
            {form.id ? `編輯技能 · ${form.id}` : '新增技能'}
          </h3>
          <div className="grid gap-2 lg:grid-cols-2">
            <label className="text-[10px] text-[var(--console-sub)]">名稱 *
              <input className={`${inputCls} mt-1`} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：部署更新流程" />
            </label>
            <label className="text-[10px] text-[var(--console-sub)]">適用時機（trigger）
              <input className={`${inputCls} mt-1`} value={form.trigger} onChange={(e) => setForm({ ...form, trigger: e.target.value })} placeholder="何時該用這條技能" />
            </label>
            <label className="text-[10px] text-[var(--console-sub)] lg:col-span-2">說明
              <input className={`${inputCls} mt-1`} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <label className="text-[10px] text-[var(--console-sub)] lg:col-span-2">內容 *（注入提示詞的知識本體）
              <textarea className={`${inputCls} mt-1 min-h-[140px] font-mono`} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} placeholder="方法論／步驟／注意事項…" />
            </label>
            <label className="text-[10px] text-[var(--console-sub)]">限定角色（逗號分隔，留空＝全角色）
              <input className={`${inputCls} mt-1`} value={form.roles} onChange={(e) => setForm({ ...form, roles: e.target.value })} placeholder="developer, reviewer, custom_linkin_*" />
            </label>
            <div className="flex items-end gap-4">
              <label className="text-[10px] text-[var(--console-sub)]">單技能字元上限
                <input type="number" className={`${inputCls} mt-1 w-28`} value={form.skill_budget} onChange={(e) => setForm({ ...form, skill_budget: Number(e.target.value) })} />
              </label>
              <label className="flex items-center gap-1.5 pb-1.5 text-[11px] text-[var(--console-sub)]">
                <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
                啟用
              </label>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" className={btnPrimaryCls} disabled={busy || !form.name.trim() || !form.content.trim()} onClick={() => void onSave()}>
              {busy ? '保存中…' : '保存'}
            </button>
            <button type="button" className={btnCls} onClick={resetForm}>取消</button>
          </div>
        </section>
      )}

      <TierSection title={t('skills.tierEnabled')} count={tiers.enabled.length}>
        <div className="grid gap-2 lg:grid-cols-2">{tiers.enabled.map(renderSkillCard)}</div>
      </TierSection>
      <TierSection title={t('skills.tierAvailable')} count={tiers.available.length} defaultOpen={false}>
        <div className="grid gap-2 lg:grid-cols-2">{tiers.available.map(renderSkillCard)}</div>
      </TierSection>
      <TierSection title={t('skills.tierNeedsKey')} count={tiers.needsKey.length} defaultOpen={false}>
        <div className="grid gap-2 lg:grid-cols-2">{tiers.needsKey.map(renderSkillCard)}</div>
      </TierSection>
      {skills.length === 0 && !editing && (
        <p className={`${consoleLayout.emptySm} text-[12px] text-[var(--console-faint)]`}>
          尚無技能。點「＋ 新技能」新增第一條——例如把公司的 SOP、代碼規範、領域知識放進去，角色執行時就會自動帶上。
        </p>
      )}
    </div>
  );
}
