/**
 * Minecraft 監控總覽 — 整頁。只展示已有的世界內容與連線事實。
 */
import AiEventsPanel from './monitor/AiEventsPanel';
import SituationStrip from './SituationStrip';
import { McHeader, McLinks, McMetrics, McPage, McPanel } from './McChrome';
import {
  PipelineTimeline,
  aiGmStatusLabel,
  bridgeLiveReady,
  bridgeNeedsSetup,
  formatAiGmLastAction,
  formatTs,
  minecraftHref,
  statusLabel,
  useMonitorSummary,
} from './monitor/shared';

export default function MonitorHubPanel() {
  const { data, error, loading, reload } = useMonitorSummary(12000);
  const ws = data?.world_status ?? {};
  const npcPending = ws.npcs?.pending_world ?? 0;
  const questPending = ws.quests?.pending_world ?? 0;
  const itemPending = ws.items?.pending_world ?? 0;
  const lastPipe = data?.last_pipeline;
  const timeline = data?.pipeline_timeline ?? [];
  const plugins = data?.plugins;
  const kpis = data?.kpis;
  const pendingBuild = kpis?.pending_build_briefs ?? 0;
  const pendingWorld = kpis?.pending_world_intents ?? 0;
  const playersLive = kpis?.players_live;
  const onlinePlayers = playersLive?.online_count ?? kpis?.online_players ?? data?.players?.online_count ?? 0;
  const summaryReady = Boolean(data) && !loading;
  const aiKpi = kpis?.ai;
  const aiStatus = aiKpi?.gm_status;
  const mapUrl = plugins?.map_url?.trim() || '';
  const bridgeSetupPending = bridgeNeedsSetup(data?.bridge, data?.bridge_setup);
  const bridgeLive = bridgeLiveReady(data?.bridge);

  const metrics = [
    { label: 'NPC', value: kpis?.npc_count ?? 0 },
    { label: '任務', value: kpis?.quest_count ?? 0 },
    { label: '道具', value: kpis?.item_count ?? 0 },
    { label: '地圖計畫', value: kpis?.map_plan_count ?? 0 },
  ];
  if (pendingBuild > 0) metrics.push({ label: '待建築', value: pendingBuild });
  if (pendingWorld > 0) metrics.push({ label: '待落地', value: pendingWorld });
  if (bridgeLive) metrics.unshift({ label: '在線玩家', value: onlinePlayers });

  const aiFacts: Array<{ label: string; value: string }> = [];
  if (aiStatus) aiFacts.push({ label: '主持人', value: aiGmStatusLabel(aiStatus) });
  if ((aiKpi?.events_24h ?? 0) > 0) aiFacts.push({ label: '24 小時事件', value: String(aiKpi?.events_24h) });
  if (aiKpi?.gm_last_run_ts) aiFacts.push({ label: '最近動作', value: formatAiGmLastAction(aiKpi) });
  if (aiKpi?.gm_enabled) {
    const mode = aiKpi.gm_dry_run ? '乾跑' : aiKpi.gm_auto_apply ? '自動套用' : '手動確認';
    aiFacts.push({ label: '套用方式', value: mode });
    if (aiKpi.gm_cooldown_seconds) aiFacts.push({ label: '冷卻', value: `${aiKpi.gm_cooldown_seconds} 秒` });
  }
  if ((aiKpi?.gm_runs_24h ?? 0) > 0) aiFacts.push({ label: '24 小時決策', value: String(aiKpi?.gm_runs_24h) });

  const worldBits = [
    npcPending > 0 ? `NPC ${npcPending}` : '',
    questPending > 0 ? `任務 ${questPending}` : '',
    itemPending > 0 ? `道具 ${itemPending}` : '',
  ].filter(Boolean);

  const next = !summaryReady
    ? null
    : bridgeSetupPending
      ? {
          title: '橋接還沒接上',
          hint: '世界內容可以先編，玩家與落地要等 MineMCP 連線。設定完成後，在線人數才會出現。',
          links: [{ href: minecraftHref('bridge_monitor'), label: '橋接健康', primary: true }],
        }
      : pendingBuild > 0
        ? {
            title: `${pendingBuild} 筆建築還在等落地`,
            hint: '到建築監控看進度，或從敘事工作區送出。',
            links: [
              { href: minecraftHref('build_monitor'), label: '建築落地', primary: true },
              { href: minecraftHref('narrative'), label: '敘事工作區' },
            ],
          }
        : pendingWorld > 0
          ? {
              title: `${pendingWorld} 筆內容還在等落地`,
              hint: worldBits.length ? `待落地：${worldBits.join('、')}` : undefined,
              links: [
                { href: minecraftHref('quest_item_monitor'), label: '任務與道具', primary: true },
                { href: minecraftHref('npc_monitor'), label: 'NPC' },
              ],
            }
          : !lastPipe && !timeline.length
            ? {
                title: '還沒跑過敘事管線',
                hint: '從敘事工作區走一輪，地圖、NPC 與任務才會進世界。',
                links: [{ href: minecraftHref('narrative'), label: '敘事工作區', primary: true }],
              }
            : !mapUrl
              ? {
                  title: '伺服器地圖還沒接上',
                  hint: '在插件中心填 Dynmap、BlueMap 或 Squaremap 的網址。',
                  links: [{ href: minecraftHref('plugin-hub'), label: '插件中心', primary: true }],
                }
              : null;

  const updated = loading ? '讀取中' : data?.generated_at ? formatTs(data.generated_at) : '';

  return (
    <McPage>
      <McHeader
        title="世界總覽"
        lead="這裡看世界裡已經有的內容，以及橋接是否真的連上伺服器。沒連上時不顯示在線人數。"
        aside={
          <>
            {updated ? <span>{updated}</span> : null}
            <button type="button" className="rd-btn" onClick={() => void reload()}>
              重新整理
            </button>
          </>
        }
      />

      {error && !data ? <p className="mc-error">{error}</p> : null}
      {error && data ? <p className="mc-error">總覽更新失敗：{error}</p> : null}
      {loading && !data ? <p className="mc-empty">正在讀取世界現況…</p> : null}

      {data ? <McMetrics items={metrics} /> : null}

      {data?.recent_errors?.length ? (
        <McPanel title="近期異常" hint={`${data.recent_errors.length} 筆`}>
          <p className="mc-note">{data.recent_errors[0]?.summary}</p>
        </McPanel>
      ) : null}

      {next ? (
        <section className="mc-callout">
          <h2 className="mc-callout__title">{next.title}</h2>
          {next.hint ? <p className="mc-callout__body">{next.hint}</p> : null}
          <McLinks links={next.links} />
        </section>
      ) : null}

      <McPanel title="四維情境" hint="市況、經濟、地土、玩家">
        <SituationStrip embedded />
      </McPanel>

      {aiFacts.length ? (
        <McPanel
          title="AI 主持人"
          action={<McLinks links={[{ href: minecraftHref('ai_gm'), label: '打開主持人' }]} />}
        >
          <dl className="mc-facts">
            {aiFacts.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
          {aiKpi?.situation_hint ? <p className="mc-note" style={{ marginTop: 12 }}>{aiKpi.situation_hint}</p> : null}
        </McPanel>
      ) : null}

      {data ? (
      <McPanel
        title="橋接"
        hint={bridgeLive ? '已連線' : data.bridge?.dry_run ? '乾跑' : '未連線'}
        action={<McLinks links={[{ href: minecraftHref('bridge_monitor'), label: '橋接健康' }]} />}
      >
        <dl className="mc-facts">
          {data.bridge?.world ? (
            <div>
              <dt>世界</dt>
              <dd>{data.bridge.world}</dd>
            </div>
          ) : null}
          <div>
            <dt>憑證</dt>
            <dd>{data.bridge?.token_configured ? '已設定' : '未設定'}</dd>
          </div>
          {mapUrl ? (
            <div>
              <dt>地圖</dt>
              <dd>{plugins?.active_map_plugin || '已設定網址'}</dd>
            </div>
          ) : null}
          {(plugins?.configured_count ?? 0) > 0 ? (
            <div>
              <dt>插件</dt>
              <dd>
                {plugins?.reachable_count ?? 0} 可連 / {plugins?.configured_count} 已設定
              </dd>
            </div>
          ) : null}
        </dl>
      </McPanel>
      ) : null}

      {data ? (
        <McPanel
          title="最近管線"
          action={
            <McLinks
              links={[
                { href: minecraftHref('narrative'), label: '敘事工作區' },
                { href: minecraftHref('layout-preview'), label: '布局預覽' },
              ]}
            />
          }
        >
        {timeline.length > 0 ? (
          <PipelineTimeline events={timeline} />
        ) : lastPipe ? (
          <div>
            <p className="mc-row__meta">{formatTs(lastPipe.ts)}</p>
            <p className="mc-note" style={{ marginTop: 6 }}>
              {lastPipe.domain}/{lastPipe.action} · {statusLabel(lastPipe.status)}
            </p>
            <p className="mc-note">{lastPipe.summary}</p>
          </div>
        ) : (
          <p className="mc-empty">還沒有管線紀錄。</p>
        )}
      </McPanel>
      ) : null}

      <AiEventsPanel />
    </McPage>
  );
}
