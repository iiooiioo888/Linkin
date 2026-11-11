/**
 * 工作台非 tasks 分頁內容（設定／策略庫／任務列表／監控）與右欄以外的 rd-tasks 區。
 */
import type { Dispatch, SetStateAction } from 'react';
import {
  deleteCustomAgent,
  resetAgentSettings,
  updateAgentMonitorPrefs,
  updateAgentSettings,
} from '../../api/client';
import type { AgentDeskScope } from '../../lib/agentUi';
import type { AgentMonitorData, RoleAgent } from '../../types';
import type { RoleDeskTab } from '../RoleDeskLayout';
import RoleSettingsPanel, {
  draftToPayload,
  type RoleSettingsDraft,
} from '../RoleSettingsPanel';
import RoleTasksPanel from '../RoleTasksPanel';
import StrategyCatalogPanel from '../StrategyCatalogPanel';
import { RoleDeepMonitor } from './RoleDeepMonitor';
import { RoleMonitorExtras } from './RoleMonitorExtras';

export function RoleDeskPanes({
  deskTab,
  selected,
  agents,
  data,
  deskScope,
  saving,
  saveError,
  pollMs,
  setSelectedId,
  setDeskTab,
  setSaving,
  setSaveError,
  setCreating,
  setCloneFrom,
  refresh,
}: {
  deskTab: RoleDeskTab;
  selected: RoleAgent;
  agents: RoleAgent[];
  data: AgentMonitorData | null;
  deskScope: AgentDeskScope;
  saving: boolean;
  saveError: string | null;
  pollMs: number;
  setSelectedId: Dispatch<SetStateAction<string>>;
  setDeskTab: Dispatch<SetStateAction<RoleDeskTab>>;
  setSaving: Dispatch<SetStateAction<boolean>>;
  setSaveError: Dispatch<SetStateAction<string | null>>;
  setCreating: Dispatch<SetStateAction<boolean>>;
  setCloneFrom: Dispatch<SetStateAction<RoleAgent | null>>;
  refresh: () => Promise<void>;
}) {
  return (
                <div className="rd-tasks">
              {deskTab === 'settings' ? (
                  <div className="rd-pane">
                    <RoleSettingsPanel
                      agent={selected}
                      catalog={data?.catalog_meta}
                      agents={agents}
                      saving={saving}
                      error={saveError}
                      onCreate={
                        deskScope === 'console'
                          ? () => {
                              setCloneFrom(null);
                              setCreating(true);
                            }
                          : undefined
                      }
                      onClone={() => {
                        setCloneFrom(selected);
                        setCreating(true);
                      }}
                      onSave={async (draft: RoleSettingsDraft) => {
                        setSaving(true);
                        setSaveError(null);
                        try {
                          await updateAgentSettings(selected.id, draftToPayload(draft));
                          await refresh();
                        } catch (err) {
                          setSaveError((err as Error).message);
                        } finally {
                          setSaving(false);
                        }
                      }}
                      onReset={
                        selected.is_custom
                          ? undefined
                          : async () => {
                              setSaving(true);
                              setSaveError(null);
                              try {
                                await resetAgentSettings(selected.id);
                                await refresh();
                              } catch (err) {
                                setSaveError((err as Error).message);
                              } finally {
                                setSaving(false);
                              }
                            }
                      }
                      onDelete={
                        selected.is_custom
                          ? async () => {
                              if (!window.confirm(`確定刪除「${selected.name}」？`)) return;
                              setSaving(true);
                              setSaveError(null);
                              try {
                                await deleteCustomAgent(selected.id);
                                setSelectedId('manager');
                                await refresh();
                              } catch (err) {
                                setSaveError((err as Error).message);
                              } finally {
                                setSaving(false);
                              }
                            }
                          : undefined
                      }
                    />
                  </div>
              ) : deskTab === 'quant' ? (
                <>
                  <div className="rd-th">
                    <h2>回測策略庫</h2>
                    <a href="#/monitor/lab/quant" className="rd-btn text-[11px] text-[var(--console-accent)]">
                      實驗室全屏
                    </a>
                    <a href="#/monitor/lab/maps" className="rd-btn text-[11px] text-[var(--console-accent)]">
                      策略圖
                    </a>
                  </div>
                  <div className="rd-pane">
                    <StrategyCatalogPanel embedded />
                  </div>
                </>
              ) : deskTab === 'list' ? (
                <>
                  <div className="rd-th">
                    <h2>任務列表 — 公司任務 {selected.company_tasks?.length ?? 0} · 工作項 {selected.work_items.length}</h2>
                  </div>
                  <div className="rd-pane">
                    <RoleTasksPanel
                      agent={selected}
                      onOpenTask={(taskId) => {
                        window.location.hash = `#/task/${encodeURIComponent(taskId)}`;
                      }}
                    />
                  </div>
                </>
              ) : deskTab === 'monitor' ? (
                <>
                  <div className="rd-th"><h2>角色監控</h2></div>
                  <div className="rd-stack">
                    <RoleDeepMonitor agent={selected} />
                    <section className="rd-sec">
                      <div className="rd-tt">角色專屬</div>
                      <RoleMonitorExtras
                        agent={selected}
                        onOpenQuant={() => setDeskTab('quant')}
                      />
                    </section>
                    <section className="rd-sec">
                      <div className="rd-tt">監控偏好</div>
                      <div className="rd-prefs">
                        <button
                          type="button"
                          className="rd-btn"
                          onClick={() => void updateAgentMonitorPrefs({ poll_interval_ms: pollMs === 5000 ? 8000 : 5000 }).then(() => refresh())}
                        >
                          輪詢 {pollMs / 1000}s
                        </button>
                        <button
                          type="button"
                          className={`rd-btn ${data?.monitor_prefs?.show_idle === false ? '' : 'on'}`}
                          onClick={() => void updateAgentMonitorPrefs({ show_idle: !(data?.monitor_prefs?.show_idle ?? true) }).then(() => refresh())}
                        >
                          待命
                        </button>
                        <button
                          type="button"
                          className={`rd-btn ${data?.monitor_prefs?.highlight_alerts === false ? '' : 'on'}`}
                          onClick={() =>
                            void updateAgentMonitorPrefs({ highlight_alerts: !(data?.monitor_prefs?.highlight_alerts ?? true) }).then(() => refresh())
                          }
                        >
                          突顯告警
                        </button>
                        <button
                          type="button"
                          className={`rd-btn ${data?.monitor_prefs?.auto_open_busy ? 'on' : ''}`}
                          onClick={() =>
                            void updateAgentMonitorPrefs({ auto_open_busy: !(data?.monitor_prefs?.auto_open_busy ?? false) }).then(() => refresh())
                          }
                        >
                          忙碌自動切入
                        </button>
                        <select
                          value={data?.monitor_prefs?.sort_by || 'level'}
                          onChange={(e) => void updateAgentMonitorPrefs({ sort_by: e.target.value }).then(() => refresh())}
                          className="rd-btn"
                        >
                          <option value="level">排序：層級</option>
                          <option value="name">排序：名稱</option>
                          <option value="status">排序：狀態</option>
                          <option value="cost">排序：花費</option>
                          <option value="queue">排序：佇列</option>
                        </select>
                        <select
                          value={data?.monitor_prefs?.group_by === 'category' ? 'category' : 'level'}
                          onChange={(e) => void updateAgentMonitorPrefs({ group_by: e.target.value }).then(() => refresh())}
                          className="rd-btn"
                        >
                          <option value="level">分組：層級</option>
                          <option value="category">分組：分類</option>
                        </select>
                      </div>
                    </section>
                  </div>
                </>
              ) : null}
                </div>
  );
}
