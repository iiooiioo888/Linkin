/**
 * IntegrationsPanel — MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil 控制台。
 *
 * 契約對齊：
 * - 啟用為顯式開關（C-INTEG-002）
 * - 召回／任務／訪談／設計皆為按需動作；禁止自動灌入審計分數
 * - 側欄資訊預設折疊；審計結果不佔常駐分數槽（C-UI-001）
 * - 深鏈：#/monitor/integrations/{name} 聚焦對應卡片
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchIntegrations, toggleIntegration } from '../../api/integrations';
import type { IntegrationGroup, IntegrationStatus } from '../../api/integrations';
import IntegrationsStrip from '../IntegrationsStrip';
import {
  GROUP_LABEL,
  INTEGRATION_META,
  jumpToIntegration,
  parseIntegrationFocus,
  summarizeIntegrations,
  type IntegrationName,
} from '../../lib/integrationsUi';
import { jumpToContextMonitor } from '../../lib/rahoUi';
import { openChatContextDetail } from '../../lib/contextUi';
import { PanelSection, PanelShell, consoleLayout } from '../ui/ConsoleLayout';
import { IntegrationCard } from './IntegrationCard';
import { OpenPencilActions } from './OpenPencilActions';
import { OuroborosActions } from './OuroborosActions';
import { RecallWorkbench } from './RecallWorkbench';
import { YaoActions } from './YaoActions';
import { btnCls } from './helpers';
import { ErrorBar, OkBar } from './shared';

export default function IntegrationsPanel() {
  const [items, setItems] = useState<IntegrationStatus[]>([]);
  const [busyName, setBusyName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [focus, setFocus] = useState<IntegrationName | null>(() => parseIntegrationFocus());

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await fetchIntegrations());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
    const t = setInterval(() => void load(), 12000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => {
    const onHash = () => setFocus(parseIntegrationFocus());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const byGroup = useMemo(() => {
    const order: IntegrationGroup[] = ['recall', 'agent', 'design'];
    return order.map((group) => ({
      group,
      meta: GROUP_LABEL[group],
      items: items.filter((i) => i.group === group),
    }));
  }, [items]);

  const recallEnabled = items.some((i) => i.group === 'recall' && i.enabled);
  const summary = summarizeIntegrations(items);

  const onToggle = async (name: string, enabled: boolean) => {
    setBusyName(name);
    setError(null);
    setMessage(null);
    try {
      const out = await toggleIntegration(name, enabled);
      if (!out.ok) {
        setError(out.error_code || '切換失敗');
      } else {
        setMessage(`${name} 已${enabled ? '啟用' : '停用'}（顯式動作）`);
        await load();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusyName(null);
    }
  };

  const actionBody = (name: string) => {
    if (name === 'yao') return <YaoActions />;
    if (name === 'ouroboros') return <OuroborosActions />;
    if (name === 'openpencil') return <OpenPencilActions />;
    const meta = INTEGRATION_META[name as IntegrationName];
    return (
      <p className="text-[11px] text-[var(--console-sub)]">
        {meta?.hint || '此整合經「召回試跑」編排'}；亦可於記憶面板查看注入結果。
      </p>
    );
  };

  return (
    <PanelShell>
      <PanelSection>
      <header className="integ-hero">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2>外部整合運行時</h2>
            <p>
              MemOS · OpenViking · WeKnora · Yao · Ouroboros · OpenPencil。預設關閉；啟用、網址與金鑰只寫入目前登入帳號。fail-open
              不阻斷主任務。深鏈：
              <code className="ml-1 text-[10px] text-[var(--console-sub)]">#/monitor/integrations/memos</code>
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full border border-white/[0.08] px-2.5 py-1 text-[10px] text-[var(--console-sub)]">
              已啟用 {summary.enabled}/{summary.total}
              {summary.degraded ? ` · 降級 ${summary.degraded}` : ''}
            </span>
            <button type="button" className={btnCls} onClick={() => openChatContextDetail()}>
              Context 詳細區
            </button>
            <button type="button" className={btnCls} onClick={() => jumpToContextMonitor()}>
              Context 鏡像
            </button>
            <button type="button" className={btnCls} onClick={() => void load()}>
              重新整理
            </button>
          </div>
        </div>
        <IntegrationsStrip
          items={items}
          density="comfortable"
          showSummary={false}
          onFocus={(name) => {
            setFocus(name);
            jumpToIntegration(name);
          }}
        />
      </header>

      <ErrorBar message={error} />
      <OkBar message={message} />

      <div className="mb-4">
        <RecallWorkbench enabled={recallEnabled} />
      </div>

      <div className="space-y-4">
        {byGroup.map(({ group, meta, items: groupItems }) => (
          <section key={group}>
            <div className="mb-2">
              <h3 className="text-[12px] font-semibold tracking-wide text-[var(--console-ink)]">{meta.label}</h3>
              <p className="text-[10px] text-[var(--console-faint)]">{meta.hint}</p>
            </div>
            <div className={consoleLayout.cardGrid}>
              {groupItems.map((item) => (
                <IntegrationCard
                  key={item.name}
                  item={item}
                  busy={busyName === item.name}
                  focused={focus === item.name}
                  forceOpen={focus === item.name && item.enabled}
                  onToggle={(enabled) => void onToggle(item.name, enabled)}
                  onSaved={(text) => {
                    setError(null);
                    setMessage(text);
                    void load();
                  }}
                  onError={(text) => {
                    setMessage(null);
                    setError(text);
                  }}
                >
                  {actionBody(item.name)}
                </IntegrationCard>
              ))}
            </div>
          </section>
        ))}
      </div>
      </PanelSection>
    </PanelShell>
  );
}
