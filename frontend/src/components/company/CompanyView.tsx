/**
 * CompanyView — 公司運行時整頁（#/company）。
 *
 * 主內容區整頁鋪開：交辦、席位樓層，以及進行中的公司任務。
 * 資料只讀既有 GET /monitor/agents。交辦不在此頁建任務，
 * 而是交給對話的同一條發送路徑，由任務經理分析後執行。
 */
import { useEffect, useMemo, useState } from 'react';
import { fetchAgentMonitor } from '../../api/client';
import { AGENT_STATUS_META, CATEGORY_LABEL } from '../../lib/agentUi';
import { COMPANY_TEMPLATES, type AgentCompanyTask, type AgentMonitorData, type CompanyTemplate, type RoleAgent } from '../../types';
import ErrorState from '../ui/ErrorState';
import './company.css';

const POLL_MS = 8000;

const TEMPLATE_NOTE: Partial<Record<CompanyTemplate, string>> = {
  quick_task: '精簡團隊',
  page_dev: '前端為主',
  fullstack_app: '完整團隊',
  research_report: '研究為主',
  story_studio: '情節、世界觀、建造',
  full_company: '全角色啟用',
};

const TASK_STATUS: Record<string, string> = {
  pending: '排隊',
  running: '執行中',
  completed: '完成',
  failed: '失敗',
  cancelled: '已取消',
  interrupted: '中斷',
};

const STATUS_RANK: Record<string, number> = {
  busy: 0,
  waiting: 1,
  error: 2,
  idle: 3,
  disabled: 4,
};

type FloorFilter = 'all' | 'live' | 'alert';

interface LiveTask extends AgentCompanyTask {
  owners: string[];
}

interface CompanyViewProps {
  onOpenRole: (roleId: string) => void;
  /** 交辦走對話同一條發送路徑，由任務經理分析並執行。 */
  onLaunch: (brief: string, template: CompanyTemplate) => void;
  onOpenTask: (taskId: string) => void;
  onOpenRaho: () => void;
}

function seatDotClass(status: string | undefined): string {
  if (status === 'busy') return 'company-dot is-busy';
  if (status === 'waiting') return 'company-dot is-waiting';
  if (status === 'error') return 'company-dot is-error';
  if (status === 'disabled') return 'company-dot is-disabled';
  return 'company-dot';
}

function isLive(agent: RoleAgent): boolean {
  return agent.status === 'busy' || agent.status === 'waiting' || agent.status === 'error' || agent.executing > 0 || agent.queue > 0;
}

function isAlert(agent: RoleAgent): boolean {
  return agent.status === 'error' || agent.budget_over === true || (agent.alerts?.length ?? 0) > 0;
}

function matchesQuery(agent: RoleAgent, query: string): boolean {
  if (!query) return true;
  const blob = [
    agent.name,
    agent.id,
    agent.level_label,
    CATEGORY_LABEL[agent.category] ?? agent.category,
    ...(agent.responsibilities ?? []),
  ]
    .join(' ')
    .toLowerCase();
  return blob.includes(query);
}

function collectTasks(agents: RoleAgent[]): LiveTask[] {
  const map = new Map<string, LiveTask>();
  for (const agent of agents) {
    for (const task of agent.company_tasks ?? []) {
      if (!task.task_id) continue;
      const prev = map.get(task.task_id);
      if (!prev) {
        map.set(task.task_id, { ...task, owners: [agent.name] });
        continue;
      }
      if (!prev.owners.includes(agent.name)) prev.owners.push(agent.name);
      if (task.status === 'running') prev.status = task.status;
    }
  }
  const rank = (status: string) => (status === 'running' ? 0 : status === 'pending' ? 1 : 2);
  return [...map.values()].sort((a, b) => rank(a.status) - rank(b.status) || a.query.localeCompare(b.query, 'zh-Hant'));
}

export default function CompanyView({ onOpenRole, onLaunch, onOpenTask, onOpenRaho }: CompanyViewProps) {
  const [data, setData] = useState<AgentMonitorData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const [brief, setBrief] = useState('');
  const [template, setTemplate] = useState<CompanyTemplate>('quick_task');
  const [floorQuery, setFloorQuery] = useState('');
  const [floorFilter, setFloorFilter] = useState<FloorFilter>('all');

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const next = await fetchAgentMonitor();
        if (cancelled) return;
        setData(next);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message || '讀取公司名冊失敗');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [nonce]);

  const agents = data?.agents ?? [];
  const query = floorQuery.trim().toLowerCase();
  const tasks = useMemo(() => collectTasks(agents), [agents]);

  const departments = useMemo(() => {
    const groups = new Map<string, RoleAgent[]>();
    for (const agent of agents) {
      if (floorFilter === 'live' && !isLive(agent)) continue;
      if (floorFilter === 'alert' && !isAlert(agent)) continue;
      if (!matchesQuery(agent, query)) continue;
      const key = agent.category || 'other';
      const list = groups.get(key) ?? [];
      list.push(agent);
      groups.set(key, list);
    }
    for (const list of groups.values()) {
      list.sort(
        (a, b) =>
          (STATUS_RANK[a.status] ?? 9) - (STATUS_RANK[b.status] ?? 9) ||
          a.name.localeCompare(b.name, 'zh-Hant'),
      );
    }
    return [...groups.entries()].sort((a, b) => {
      const labelA = CATEGORY_LABEL[a[0]] ?? a[0];
      const labelB = CATEGORY_LABEL[b[0]] ?? b[0];
      return labelA.localeCompare(labelB, 'zh-Hant');
    });
  }, [agents, floorFilter, query]);

  const summary = data?.summary;

  const launch = () => {
    const text = brief.trim();
    if (!text) return;
    setBrief('');
    onLaunch(text, template);
  };

  return (
    <div className="company-page">
      <div className="company-page__scroll">
        <div className="company-page__inner">
          <header>
            <p className="company-kicker">公司運行時</p>
            <h1 className="company-title">公司</h1>
            <p className="company-lead">
              在這裡看席位。要交辦時寫下目標，會回到對話，由任務經理分析後執行。
            </p>
            <div className="company-actions">
              <button type="button" className="rd-btn" onClick={() => setNonce((n) => n + 1)}>
                重新整理
              </button>
              <button type="button" className="rd-btn" onClick={onOpenRaho}>
                席位投遞
              </button>
            </div>
          </header>

          {summary ? (
            <section className="company-metrics" aria-label="公司現況">
              <Metric label="席位" value={summary.roles_total} />
              <Metric label="執行中" value={summary.roles_busy} />
              <Metric label="等待" value={summary.roles_waiting} />
              <Metric label="進行中的公司任務" value={summary.running_company_tasks} />
              <Metric label="未完成工作項" value={summary.work_items_open} />
            </section>
          ) : null}

          <section className="company-panel" aria-label="交辦">
            <div className="company-panel__head">
              <h2 className="company-panel__title">交辦</h2>
              <span className="company-panel__hint">寫下目標後回到對話，由任務經理分析並執行</span>
            </div>
            <div className="company-dispatch">
              <label className="block">
                <span className="sr-only">要完成的事</span>
                <textarea
                  className="company-field"
                  value={brief}
                  placeholder="寫下要公司完成的事。例如：把登入頁改成深色，並補上錯誤狀態。"
                  onChange={(event) => setBrief(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
                      event.preventDefault();
                      void launch();
                    }
                  }}
                />
              </label>
              <div>
                <p className="company-panel__hint" style={{ marginBottom: 8 }}>
                  組織模板
                </p>
                <div className="company-templates" role="radiogroup" aria-label="組織模板">
                  {COMPANY_TEMPLATES.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      role="radio"
                      aria-checked={template === item.value}
                      className={`company-template${template === item.value ? ' is-on' : ''}`}
                      onClick={() => setTemplate(item.value)}
                    >
                      <span className="company-template__name">{item.label}</span>
                      {TEMPLATE_NOTE[item.value] ? (
                        <span className="company-template__note">{TEMPLATE_NOTE[item.value]}</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <div className="company-dispatch__foot">
              <button type="button" className="company-submit" disabled={!brief.trim()} onClick={launch}>
                交辦到對話
              </button>
              <span className="company-panel__hint">Ctrl + Enter 送出</span>
            </div>
          </section>

          {error && !data ? (
            <ErrorState message={error} onRetry={() => setNonce((n) => n + 1)} />
          ) : null}
          {error && data ? <p className="company-error">名冊更新失敗：{error}</p> : null}
          {loading && !data ? <p className="company-empty">正在讀取公司名冊…</p> : null}

          <section className="company-panel" aria-label="席位樓層">
            <div className="company-panel__head">
              <h2 className="company-panel__title">席位</h2>
              <span className="company-panel__hint">任務經理由這裡的席位執行</span>
            </div>
            <div className="company-filters">
              <input
                className="company-search"
                value={floorQuery}
                placeholder="搜尋席位、職責"
                aria-label="搜尋席位"
                onChange={(event) => setFloorQuery(event.target.value)}
              />
              {([
                ['all', '全部'],
                ['live', '有工作'],
                ['alert', '需留意'],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`rd-btn${floorFilter === key ? ' on' : ''}`}
                  onClick={() => setFloorFilter(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            {!data ? null : departments.length === 0 ? (
              <p className="company-empty" style={{ marginTop: 12 }}>
                這個篩選下沒有席位。
              </p>
            ) : (
              <div className="company-depts" style={{ marginTop: 12 }}>
                {departments.map(([category, list]) => (
                  <article key={category} className="company-dept">
                    <div className="company-dept__head">
                      <h3 className="company-dept__name">{CATEGORY_LABEL[category] ?? category}</h3>
                      <span className="company-dept__count">{list.length}</span>
                    </div>
                    <ul className="company-roles">
                      {list.map((agent) => (
                        <li key={agent.id}>
                          <button type="button" className="company-role" onClick={() => onOpenRole(agent.id)}>
                            <span className={seatDotClass(agent.status)} aria-hidden />
                            <span className="company-role__name">{agent.name}</span>
                            <span className="company-role__tag">
                              {AGENT_STATUS_META[agent.status]?.label ?? agent.status}
                              {agent.executing > 0 ? ` · ${agent.executing}` : ''}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </article>
                ))}
              </div>
            )}
          </section>

          <section className="company-panel" aria-label="公司任務">
            <div className="company-panel__head">
              <h2 className="company-panel__title">公司任務</h2>
              <span className="company-panel__hint">{tasks.length} 筆出現在席位上</span>
            </div>
            {!data ? (
              <p className="company-empty">名冊載入後，進行中的公司任務會列在這裡。</p>
            ) : tasks.length === 0 ? (
              <p className="company-empty">目前沒有掛在席位上的公司任務。交辦到對話之後，進行中的任務會出現在這裡。</p>
            ) : (
              <div className="company-tasks">
                {tasks.map((task) => (
                  <button key={task.task_id} type="button" className="company-task" onClick={() => onOpenTask(task.task_id)}>
                    <span className="company-task__status">{TASK_STATUS[task.status] ?? task.status}</span>
                    <span className="company-task__query">{task.query || task.task_id}</span>
                    <span className="company-task__owners">{task.owners.slice(0, 3).join('、')}</span>
                  </button>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="company-metric">
      <div className="company-metric__value">{value}</div>
      <div className="company-metric__label">{label}</div>
    </div>
  );
}
