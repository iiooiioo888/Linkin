/**
 * Docker 與阿里雲區塊。數字都是版面範例，不連線、不寫入。
 */
import { useState } from 'react';

const CONTAINERS = [
  ['linkin-backend', '8000', '範例'],
  ['linkin-frontend', '3001', '範例'],
  ['linkin-opc', '8001', '範例'],
  ['linkin-redis', '6379', '範例'],
  ['linkin-chroma', '8100', '範例'],
  ['linkin-watchtower', '—', 'RESTARTING · 範例'],
] as const;

const COMMANDS = [
  'docker compose up -d',
  'docker compose logs -f backend',
  'docker compose ps',
  'docker compose prune',
  'docker stats',
] as const;

const TILES = [
  ['ECS', '4'],
  ['RDS', '2'],
  ['OSS', '1.24TB'],
  ['SLB', '2'],
  ['Redis', '3'],
  ['ACR', '5'],
] as const;

const COSTS = [
  ['ECS', '¥3240', '52.4%'],
  ['RDS', '¥1880', '30.4%'],
  ['OSS', '¥420', '6.8%'],
  ['流量', '¥380', '6.1%'],
  ['SLB', '¥260', '4.2%'],
] as const;

const ECS_ROWS = [
  ['i-example-a', '運行中'],
  ['i-example-b', '運行中'],
  ['i-example-c', '運行中'],
  ['i-example-d', '維護中'],
] as const;

const BILLS = [
  ['ECS', '¥3240', '已列'],
  ['RDS', '¥1880', '已列'],
  ['OSS', '¥420', '已列'],
  ['流量', '¥380', '已列'],
  ['SLB', '¥260', '已列'],
  ['合計', '¥6180', '待對帳'],
] as const;

export function InfraSections() {
  const [picked, setPicked] = useState('未執行。這些指令只顯示，不送出。');

  return (
    <>
      <section className="panel infra-docker" id="c-docker">
        <div className="panel-head">
          <h2 className="panel-title">
            Docker Compose
            <span className="en">CONTAINERS</span>
          </h2>
          <span className="pill or">範例</span>
        </div>
        <div className="stats docker-stats">
          {[
            ['6/6', '健康'],
            ['34%', 'CPU'],
            ['2.8/8GB', '記憶體'],
            ['9', '映像'],
            ['218h', '本月'],
            ['範例', '來源'],
          ].map(([num, label]) => (
            <div key={label} className="stat">
              <div className="stat-num is-docker">{num}</div>
              <div className="stat-label">{label}</div>
            </div>
          ))}
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>容器</th>
              <th>埠</th>
              <th>狀態</th>
              <th>動作</th>
            </tr>
          </thead>
          <tbody>
            {CONTAINERS.map(([name, port, health]) => (
              <tr key={name}>
                <td className="strong">{name}</td>
                <td className="mono">{port}</td>
                <td className="mono">{health}</td>
                <td>
                  <button type="button" className="infra-act" onClick={() => setPicked(`範例，未執行：docker compose logs -f ${name}`)}>
                    看指令
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="panel-body infra-split">
          <svg className="topo" viewBox="0 0 360 150" role="img" aria-label="Compose 拓撲範例">
            <rect className="topo-node is-docker" x="16" y="58" width="88" height="32" rx="4" />
            <text className="topo-label" x="60" y="78" textAnchor="middle">frontend</text>
            <rect className="topo-node is-docker" x="136" y="58" width="88" height="32" rx="4" />
            <text className="topo-label" x="180" y="78" textAnchor="middle">backend</text>
            <path className="topo-line" d="M104 74 H136" />
            <rect className="topo-node" x="250" y="16" width="90" height="26" rx="4" />
            <text className="topo-label" x="295" y="33" textAnchor="middle">redis</text>
            <rect className="topo-node" x="250" y="58" width="90" height="26" rx="4" />
            <text className="topo-label" x="295" y="75" textAnchor="middle">chroma</text>
            <rect className="topo-node is-data" x="250" y="100" width="90" height="26" rx="4" />
            <text className="topo-label is-data" x="295" y="117" textAnchor="middle">opc</text>
            <path className="topo-line" d="M224 74 H250 M270 74 V42 M270 74 V113" />
            <rect className="topo-cloud" x="16" y="112" width="150" height="28" rx="4" />
            <text className="topo-label is-cloud" x="91" y="130" textAnchor="middle">阿里雲 · 唯讀</text>
          </svg>
          <div>
            <p className="kicker">常用指令 · 範例</p>
            <ul className="cmd-list">
              {COMMANDS.map((cmd) => (
                <li key={cmd}>
                  <button type="button" className="infra-act" onClick={() => setPicked(`範例，未執行：${cmd}`)}>
                    {cmd}
                  </button>
                </li>
              ))}
            </ul>
            <p className="console-empty">{picked}</p>
          </div>
        </div>
      </section>

      <section className="panel infra-cloud" id="c-aliyun">
        <div className="panel-head">
          <h2 className="panel-title">
            阿里雲
            <span className="en">READ ONLY</span>
          </h2>
          <span className="pill vi">範例 · cn-hangzhou</span>
        </div>
        <div className="panel-body">
          <p className="console-empty">RAM linkin-readonly。沒有呼叫雲端 API。</p>
          <div className="cloud-tiles">
            {TILES.map(([name, value]) => (
              <div key={name} className="cloud-tile">
                <strong>{value}</strong>
                <span>{name}</span>
                <em>範例</em>
              </div>
            ))}
          </div>
          <div className="cost-list">
            {COSTS.map(([name, money, share]) => (
              <div key={name} className="cost-row">
                <span>{name}</span>
                <span className="cost-bar"><span style={{ width: share }} /></span>
                <span className="mono">{money} 範例</span>
              </div>
            ))}
          </div>
          <div className="budget" aria-label="預算範例 77.2%">
            <span>預算 77.2% / ¥8000</span>
            <em>範例</em>
          </div>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>ECS</th>
              <th>狀態</th>
            </tr>
          </thead>
          <tbody>
            {ECS_ROWS.map(([id, status]) => (
              <tr key={id}>
                <td className="mono">{id}</td>
                <td>{status} · 範例</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table className="table">
          <thead>
            <tr>
              <th>帳項</th>
              <th>金額</th>
              <th>對帳</th>
            </tr>
          </thead>
          <tbody>
            {BILLS.map(([name, money, state]) => (
              <tr key={name}>
                <td>{name}</td>
                <td className="mono">{money}</td>
                <td>{state} · 範例</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

export function InfraRailNotes() {
  return (
    <>
      <section className="sensor" aria-label="Docker 時數">
        <div className="panel-head">
          <h2 className="panel-title">Docker 時數<span className="en">HOURS</span></h2>
        </div>
        <div className="row-kv"><span>本月</span><span className="v is-docker">218/300h 範例</span></div>
        <div className="row-kv"><span>單價</span><span className="v is-docker">10 積分/小時 範例</span></div>
      </section>
      <section className="sensor" aria-label="阿里雲帳單">
        <div className="panel-head">
          <h2 className="panel-title">阿里雲<span className="en">BILLING</span></h2>
        </div>
        <div className="row-kv"><span>對帳</span><span className="v is-cloud">¥6180 範例</span></div>
        <div className="row-kv"><span>權限</span><span className="v is-cloud">唯讀</span></div>
      </section>
    </>
  );
}
