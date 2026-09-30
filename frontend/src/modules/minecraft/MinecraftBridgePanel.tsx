/**
 * MinecraftBridgePanel — MineMCP 連線狀態、工具呼叫與審計。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  callMinecraftTool,
  fetchMinecraftStatus,
  probeMinecraft,
  type MinecraftStatus,
} from '../../api/linkin';
import { navPathForTab } from '../../lib/monitorTabs';
import { McHeader, McMetrics, McPage, McPanel } from './McChrome';

const TOOL_LABELS: Record<string, string> = {
  place_block: '放置方塊',
  pose_block: '遠端放置',
  break_block: '破壞方塊',
  fill_block: '填充區域',
  execute_command: '執行指令',
  get_player: '查詢玩家',
  get_online_players: '在線玩家',
};

export default function MinecraftBridgePanel() {
  const [status, setStatus] = useState<MinecraftStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<'idle' | 'probe' | 'call'>('idle');
  const [tool, setTool] = useState('place_block');
  const [x, setX] = useState('100');
  const [y, setY] = useState('64');
  const [z, setZ] = useState('200');
  const [x2, setX2] = useState('104');
  const [y2, setY2] = useState('68');
  const [z2, setZ2] = useState('204');
  const [material, setMaterial] = useState('DIAMOND_BLOCK');
  const [player, setPlayer] = useState('');
  const [command, setCommand] = useState('time set day');
  const [confirmed, setConfirmed] = useState(false);
  const [dryRunAck, setDryRunAck] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setStatus(await fetchMinecraftStatus());
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onProbe = async () => {
    setBusy('probe');
    setError(null);
    try {
      await probeMinecraft();
      await load();
      setMessage('探測完成');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const onCall = async () => {
    setBusy('call');
    setError(null);
    setMessage(null);
    const args: Record<string, unknown> = {};
    if (tool === 'place_block' || tool === 'pose_block' || tool === 'break_block') {
      args.x = Number(x);
      args.y = Number(y);
      args.z = Number(z);
      if (tool !== 'break_block') args.material = material;
    } else if (tool === 'fill_block') {
      args.x1 = Number(x);
      args.y1 = Number(y);
      args.z1 = Number(z);
      args.x2 = Number(x2);
      args.y2 = Number(y2);
      args.z2 = Number(z2);
      args.material = material;
    } else if (tool === 'get_player') {
      args.player = player;
    } else if (tool === 'execute_command') {
      args.command = command;
      args.confirmed = confirmed;
    }
    try {
      const data = await callMinecraftTool(tool, args);
      setResult(data);
      setMessage(data.ok ? '已送出（見結果）' : String(data.error || '失敗'));
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy('idle');
    }
  };

  const mode = status?.dry_run ? '乾跑' : status?.connected ? '已連線' : '未連線';

  const executeBlock = useMemo(() => {
    if (!status?.token_configured) {
      return { disabled: true, reason: 'Token 未設定 — 請配置 EVOL_MC_MCP_TOKEN 後再執行工具。' };
    }
    if (status.dry_run && !dryRunAck) {
      return {
        disabled: true,
        reason: '目前為乾跑模式：勾選下方確認後才可送出（不會寫入世界）。',
      };
    }
    if (!status.connected && !status.dry_run) {
      return { disabled: true, reason: '橋接未連線 — 請先完成啟用並 Ping 探測。' };
    }
    if (tool === 'execute_command' && !confirmed) {
      return { disabled: true, reason: 'execute_command 需勾選「敏感操作已二次確認」。' };
    }
    return { disabled: false, reason: '' };
  }, [status, dryRunAck, tool, confirmed]);

  const metrics = [
    { label: '模式', value: mode },
    { label: '憑證', value: status?.token_configured ? '已設定' : '未設定' },
    { label: '方塊上限', value: status?.max_blocks ?? 5000 },
  ];
  if (status?.world) metrics.splice(1, 0, { label: '世界', value: status.world });

  return (
    <McPage>
      <McHeader
        title="橋接"
        lead={`寫入都經過護欄。乾跑只記審計，不會改世界。建築檔在「${navPathForTab('building')}」。`}
        aside={
          <>
            <button type="button" onClick={() => void load()} className="mc-btn">重新整理</button>
            <button type="button" disabled={busy !== 'idle'} onClick={() => void onProbe()} className="mc-btn is-primary">
              {busy === 'probe' ? '探測中' : '探測連線'}
            </button>
          </>
        }
      />
      <div className="mc-workspace">
      {error && <p className="mc-error">{error}</p>}
      {message && <p className="mc-note">{message}</p>}
      {status ? <McMetrics items={metrics} /> : null}
      {status?.url ? <p className="mc-note">端點 {status.url}</p> : null}

      <McPanel title="寫入世界" hint="經護欄送出">
        <div className="mc-form">
          <label>工具
            <select value={tool} onChange={(e) => setTool(e.target.value)}>
              {(status?.company_tools ?? ['place_block', 'break_block', 'fill_block', 'execute_command', 'get_player', 'get_online_players']).map((name) => (
                <option key={name} value={name}>{TOOL_LABELS[name] ?? name}</option>
              ))}
            </select>
          </label>
          {(tool === 'place_block' || tool === 'pose_block' || tool === 'break_block' || tool === 'fill_block') && (
            <>
              <label>{tool === 'fill_block' ? '起點 x, y, z' : '座標 x, y, z'}
                <div className="mc-coords">
                  <input aria-label="x" value={x} onChange={(e) => setX(e.target.value)} />
                  <input aria-label="y" value={y} onChange={(e) => setY(e.target.value)} />
                  <input aria-label="z" value={z} onChange={(e) => setZ(e.target.value)} />
                </div>
              </label>
              {tool === 'fill_block' && (
                <label>終點 x, y, z
                  <div className="mc-coords">
                    <input aria-label="x2" value={x2} onChange={(e) => setX2(e.target.value)} />
                    <input aria-label="y2" value={y2} onChange={(e) => setY2(e.target.value)} />
                    <input aria-label="z2" value={z2} onChange={(e) => setZ2(e.target.value)} />
                  </div>
                </label>
              )}
              {tool !== 'break_block' && (
                <label>材料
                  <input value={material} onChange={(e) => setMaterial(e.target.value)} />
                </label>
              )}
            </>
          )}
          {tool === 'get_player' && (
            <label>玩家
              <input value={player} onChange={(e) => setPlayer(e.target.value)} />
            </label>
          )}
          {tool === 'execute_command' && (
            <>
              <label>指令
                <input value={command} onChange={(e) => setCommand(e.target.value)} />
              </label>
              <label className="mc-check">
                <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                敏感操作已二次確認
              </label>
            </>
          )}
        </div>
        {status?.dry_run ? (
          <label className="mc-check" style={{ marginTop: 12 }}>
            <input type="checkbox" checked={dryRunAck} onChange={(e) => setDryRunAck(e.target.checked)} />
            我了解這次只記審計，不會寫入世界
          </label>
        ) : null}
        {executeBlock.reason ? <p className="mc-note" style={{ marginTop: 12 }}>{executeBlock.reason}</p> : null}
        <div className="mc-actions">
          <button
            type="button"
            disabled={busy !== 'idle' || executeBlock.disabled}
            onClick={() => void onCall()}
            className="mc-btn is-primary"
          >
            {busy === 'call' ? '送出中' : '送出'}
          </button>
        </div>
        {result && (
          <pre>{JSON.stringify(result, null, 2)}</pre>
        )}
      </McPanel>

      <McPanel title="最近操作" hint={(status?.recent?.length ?? 0) > 0 ? `${status?.recent?.length} 筆` : undefined}>
        {(status?.recent ?? []).length === 0 ? <p className="mc-empty">還沒有寫入紀錄。</p> : null}
        <ul className="mc-list">
          {(status?.recent ?? []).slice().reverse().map((row, index) => (
            <li key={`${row.ts}-${index}`} className="mc-row">
              <div className="mc-row__top">
                <span className="mc-row__title">{TOOL_LABELS[row.tool || ''] || row.tool || row.remote}</span>
                <span className="mc-row__status">{row.ok ? '成功' : '失敗'}</span>
              </div>
              <p className="mc-row__meta">
                {row.dry_run ? '乾跑 · ' : ''}
                {row.duration_ms != null ? `${row.duration_ms} ms · ` : ''}
                {row.ts}
              </p>
              {row.error ? <p className="mc-error">{row.error}</p> : null}
            </li>
          ))}
        </ul>
      </McPanel>
      </div>
    </McPage>
  );
}
