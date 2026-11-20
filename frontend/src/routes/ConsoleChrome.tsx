/**
 * 控制台視覺元件。有本機或設定資料就顯示，沒有就留空態。
 * 不填 OPC 讀數、餘額或任務。
 */
import { useEffect, useState } from 'react';
import { fetchConfig } from '../api/client/config';
import { PATH_LABEL, readSessionPathChoice } from '../lib/executionPath';
import { loadActiveSessionId, loadSessions } from '../lib/storage';
import type { SurfaceId } from './catalog';

const KICKER: Record<SurfaceId, string> = {
  chat: 'CONVERSATION',
  history: 'HISTORY',
  'context-compression': 'CONTEXT',
  'prompt-compression': 'PROMPT',
};

const ROUTE_RULES = [
  ['1', '工業關鍵詞（感測、閥門、OPC、PLC）', 'company · industrial_ops'],
  ['2', '靈境複雜任務', 'company'],
  ['5', '已開啟 cost_speed', 'company 或 simple'],
  ['6', '公司關鍵詞，或長度達到門檻', 'company，否則 simple'],
] as const;

export function useConsoleFacts() {
  const [llm, setLlm] = useState<'yes' | 'no' | 'unknown'>('unknown');
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancel = false;
    fetchConfig()
      .then((cfg) => {
        if (!cancel) setLlm(cfg.configured ? 'yes' : 'no');
      })
      .catch(() => {
        if (!cancel) setLlm('unknown');
      });
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    const bump = () => setTick((value) => value + 1);
    window.addEventListener('storage', bump);
    return () => window.removeEventListener('storage', bump);
  }, []);

  const sessions = typeof window === 'undefined' ? [] : loadSessions();
  const activeId = typeof window === 'undefined' ? null : loadActiveSessionId();
  const active = sessions.find((item) => item.id === activeId) ?? sessions[0];
  const messages = active?.messages.length ?? 0;
  const taskRows = (active?.messages ?? [])
    .filter((item) => item.taskId || item.taskState)
    .slice(0, 5)
    .map((item) => ({
      id: item.id,
      title: (item.taskState?.query || item.content || item.taskId || '任務').replace(/\s+/g, ' ').slice(0, 36),
      status: item.taskState?.status || '—',
    }));
  const path = typeof window === 'undefined' ? null : readSessionPathChoice();
  void tick;

  return { llm, sessions: sessions.length, messages, tasks: taskRows.length, taskRows, path };
}

export function ConsoleDeck({ surface, label }: { surface: SurfaceId; label: string }) {
  const facts = useConsoleFacts();
  const pathLabel = facts.path ? PATH_LABEL[facts.path.path] : null;
  const model =
    facts.llm === 'yes' ? '已設定' : facts.llm === 'no' ? '未設定' : null;

  const stats = [
    { num: facts.messages ? String(facts.messages) : '—', label: '訊息', en: 'MESSAGES', sub: facts.messages ? '本機會話' : '尚無訊息' },
    { num: String(facts.sessions), label: '會話', en: 'SESSIONS', sub: facts.sessions ? '本機儲存' : '尚無會話' },
    { num: pathLabel ?? '—', label: '路徑', en: 'PATH', sub: pathLabel ? '本次選擇' : '尚未選擇' },
    { num: model ?? '—', label: '模型', en: 'MODEL', sub: model ?? '尚未連線' },
    { num: facts.tasks ? String(facts.tasks) : '—', label: '任務', en: 'TASKS', sub: facts.tasks ? '本機會話' : '尚無任務' },
  ];

  return (
    <div className="console-deck">
      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">
            {label}
            <span className="en">{KICKER[surface]}</span>
          </h2>
        </div>
        <div className="stats" aria-label="本機概況">
          {stats.map((item) => (
            <div key={item.en} className="stat">
              <div className="stat-num">{item.num}</div>
              <div className="stat-label">
                {item.label} {item.en}
              </div>
              <div className="stat-sub">{item.sub}</div>
            </div>
          ))}
        </div>
      </section>
      <section className="panel path-panel">
        <div className="panel-head">
          <h2 className="panel-title">
            resolve_execution_path
            <span className="en">ROUTE</span>
          </h2>
        </div>
        <div className="panel-body">
          <PathDiagram />
          <p className="console-empty">沒有進行中的查詢。光點只沿文件裡的主鏈巡行。</p>
          <table className="table route-table">
            <thead>
              <tr>
                <th>順序</th>
                <th>條件</th>
                <th>路徑</th>
              </tr>
            </thead>
            <tbody>
              {ROUTE_RULES.map(([order, when, path]) => (
                <tr key={order}>
                  <td className="mono">{order}</td>
                  <td>{when}</td>
                  <td className="mono">{path}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="lock-line">
            force_company_keywords 命中時鎖定 company，decision_source 為 admin_lock。auto 已棄用。
          </p>
        </div>
      </section>
      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title">
            任務與席位
            <span className="en">TASKS</span>
          </h2>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>任務</th>
              <th>狀態</th>
              <th>席位</th>
            </tr>
          </thead>
          <tbody>
            {facts.taskRows.length === 0 ? (
              <tr>
                <td className="strong" colSpan={3}>
                  尚無任務，也尚無席位活動。
                </td>
              </tr>
            ) : (
              facts.taskRows.map((row) => (
                <tr key={row.id}>
                  <td className="strong">{row.title}</td>
                  <td className="mono">{row.status}</td>
                  <td className="mono">—</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function PathDiagram() {
  return (
    <svg className="path-diagram" viewBox="0 0 640 210" role="img" aria-label="resolve_execution_path 主鏈與 simple、company 分叉">
      <defs>
        <filter id="resolve-glow" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="0" stdDeviation="3.5" floodColor="#f0a500" floodOpacity="0.9" />
        </filter>
      </defs>
      <path id="flow-main" className="flow-line" d="M16 108 H250" />
      <path className="flow-line" d="M390 108 C430 108 438 48 500 48" />
      <path className="flow-line" d="M390 108 C430 108 438 168 500 168" />
      <path className="flow-line flow-loop" d="M548 36 C600 36 612 78 548 78" />
      <circle className="flow-dot" r="3.2">
        <animateMotion dur="3.6s" repeatCount="indefinite">
          <mpath href="#flow-main" />
        </animateMotion>
      </circle>
      {(
        [
          [16, '記憶'],
          [78, 'OPC'],
          [140, '靈境'],
          [202, '召回'],
        ] as const
      ).map(([x, name]) => (
        <g key={name} transform={`translate(${x} 108)`}>
          <rect className={name === 'OPC' ? 'flow-node is-data' : 'flow-node'} x="0" y="-16" width="52" height="32" rx="3" />
          <text className={name === 'OPC' ? 'flow-label is-data' : 'flow-label'} x="26" y="4" textAnchor="middle">
            {name}
          </text>
        </g>
      ))}
      <g filter="url(#resolve-glow)" transform="translate(320 108)">
        <polygon className="resolve-diamond" points="0,-34 36,0 0,34 -36,0" />
      </g>
      <text className="flow-label resolve-name" x="320" y="104" textAnchor="middle">
        resolve
      </text>
      <text className="flow-label resolve-name" x="320" y="118" textAnchor="middle">
        _execution_path
      </text>
      <g transform="translate(500 48)">
        <rect className="flow-node" x="0" y="-16" width="72" height="32" rx="3" />
        <text className="flow-label" x="36" y="4" textAnchor="middle">
          simple
        </text>
      </g>
      <text className="flow-label" x="590" y="44" textAnchor="middle">
        反思
      </text>
      <g transform="translate(500 168)">
        <rect className="flow-node" x="0" y="-16" width="88" height="32" rx="3" />
        <text className="flow-label" x="44" y="-1" textAnchor="middle">
          任務經理
        </text>
        <text className="flow-label" x="44" y="12" textAnchor="middle">
          80 席
        </text>
      </g>
    </svg>
  );
}

export function ConsoleRailPanels() {
  return (
    <>
      <section className="sensor" aria-label="感測">
        <div className="panel-head">
          <h2 className="panel-title">感測<span className="en">SENSOR</span></h2>
        </div>
        <div className="row-kv"><span>讀數</span><span className="v is-reading">尚無讀數</span></div>
        <div className="row-kv"><span>寫入</span><span className="v">opc_service/guard.py</span></div>
      </section>
      <section className="sensor" aria-label="樞紐">
        <div className="panel-head">
          <h2 className="panel-title">樞紐<span className="en">HUB</span></h2>
        </div>
        <div className="row-kv"><span>前端</span><span className="v">3001</span></div>
        <div className="row-kv"><span>後端</span><span className="v">8000</span></div>
        <div className="row-kv"><span>OPC</span><span className="v">8001</span></div>
        <div className="row-kv"><span>Redis</span><span className="v">6379</span></div>
        <div className="row-kv"><span>Chroma</span><span className="v">8100</span></div>
        <div className="row-kv"><span>mattpocock</span><span className="v">37</span></div>
        <div className="row-kv"><span>anthropic</span><span className="v">20</span></div>
        <div className="row-kv"><span>openai</span><span className="v">43</span></div>
        <div className="row-kv"><span>單項 CLI</span><span className="v">4</span></div>
        <div className="row-kv"><span>內嵌</span><span className="v">3</span></div>
        <div className="row-kv"><span>目錄合計</span><span className="v">107</span></div>
      </section>
      <section className="sensor" aria-label="錢包">
        <div className="panel-head">
          <h2 className="panel-title">錢包<span className="en">WALLET</span></h2>
        </div>
        <div className="row-kv"><span>月贈</span><span className="v">—</span></div>
        <div className="row-kv"><span>購買</span><span className="v">—</span></div>
        <div className="row-kv"><span>貢獻未鎖</span><span className="v">—</span></div>
        <div className="row-kv"><span>貢獻鎖定</span><span className="v">—</span></div>
        <p className="console-empty">尚無餘額。扣款只走 monthly_grant → purchased。</p>
      </section>
      <section className="sensor" aria-label="反思">
        <div className="panel-head">
          <h2 className="panel-title">反思<span className="en">REFLECTION</span></h2>
        </div>
        <div className="row-kv"><span>simple</span><span className="v">評估後反思</span></div>
        <div className="row-kv"><span>company</span><span className="v">預設不後反思</span></div>
        <div className="row-kv"><span>失敗無產出</span><span className="v">直接存檔</span></div>
      </section>
      <section className="sensor" aria-label="健康">
        <div className="panel-head">
          <h2 className="panel-title">健康<span className="en">HEALTH</span></h2>
        </div>
        <ol className="constraint-list">
          <li>LLM 只經 call_llm。</li>
          <li>測試隔離外部依賴。</li>
          <li>圖只經 build_graph()。</li>
          <li>OPC 寫入只經護欄。</li>
        </ol>
        <p className="console-empty">尚無即時檢查。</p>
      </section>
    </>
  );
}
