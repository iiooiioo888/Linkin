/**
 * MinecraftBridgePanel — MineMCP 連線狀態、工具呼叫與審計。
 */
import { useCallback, useEffect, useState } from 'react';
import {
  callMinecraftTool,
  fetchMinecraftStatus,
  probeMinecraft,
  type MinecraftStatus,
} from '../../api/linkin';

export default function MinecraftBridgePanel() {
  const [status, setStatus] = useState<MinecraftStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tool, setTool] = useState('place_block');
  const [x, setX] = useState('100');
  const [y, setY] = useState('64');
  const [z, setZ] = useState('200');
  const [material, setMaterial] = useState('DIAMOND_BLOCK');
  const [player, setPlayer] = useState('');
  const [command, setCommand] = useState('time set day');
  const [confirmed, setConfirmed] = useState(false);
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
    setBusy(true);
    setError(null);
    try {
      await probeMinecraft();
      await load();
      setMessage('探測完成');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const onCall = async () => {
    setBusy(true);
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
      args.x2 = Number(x);
      args.y2 = Number(y);
      args.z2 = Number(z);
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
      setBusy(false);
    }
  };

  const mode = status?.dry_run ? '乾跑（未連伺服器）' : status?.connected ? '已連線' : '未連線';

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto apple-canvas p-4 text-[#f7f8f8]">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">Minecraft MCP</h2>
          <p className="mt-0.5 text-[11px] text-[#8a8f98]">
            公司角色工具橋接 MineMCP（JSON-RPC）。遠端放置工具名為 pose_block。
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => void load()} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-2 py-1 text-[11px] text-[#8a8f98] hover:text-[#f7f8f8]">
            重新整理
          </button>
          <button type="button" disabled={busy} onClick={() => void onProbe()} className="rounded-xl border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-2 py-1 text-[11px] text-[#64D2FF] disabled:opacity-40">
            {busy ? '探測中' : '探測連線'}
          </button>
        </div>
      </div>

      {error && <div className="mb-3 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</div>}
      {message && <div className="mb-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">{message}</div>}

      <div className="mb-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {[
          { label: '模式', value: mode },
          { label: '世界', value: status?.world || '—' },
          { label: 'Token', value: status?.token_configured ? '已設定' : '未設定' },
          { label: '方塊上限', value: String(status?.max_blocks ?? 5000) },
        ].map((card) => (
          <div key={card.label} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] px-3 py-2">
            <p className="text-[10px] text-[#8a8f98]">{card.label}</p>
            <p className="text-sm font-medium">{card.value}</p>
          </div>
        ))}
      </div>

      <p className="mb-3 text-[11px] text-[#8a8f98]">端點 {status?.url || '—'}</p>

      <section className="mb-4 rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-[#8a8f98]">手動呼叫（經護欄）</h3>
        <div className="grid gap-2 lg:grid-cols-2">
          <label className="text-[10px] text-[#8a8f98]">工具
            <select value={tool} onChange={(e) => setTool(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-[#1C1C1E] px-2 py-1.5 text-[12px]">
              {(status?.company_tools ?? ['place_block', 'break_block', 'fill_block', 'execute_command', 'get_player', 'get_online_players']).map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          {(tool === 'place_block' || tool === 'pose_block' || tool === 'break_block' || tool === 'fill_block') && (
            <>
              <label className="text-[10px] text-[#8a8f98]">座標 x,y,z
                <div className="mt-1 grid grid-cols-3 gap-1">
                  <input value={x} onChange={(e) => setX(e.target.value)} className="rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
                  <input value={y} onChange={(e) => setY(e.target.value)} className="rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
                  <input value={z} onChange={(e) => setZ(e.target.value)} className="rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
                </div>
              </label>
              {tool !== 'break_block' && (
                <label className="text-[10px] text-[#8a8f98]">材料
                  <input value={material} onChange={(e) => setMaterial(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
                </label>
              )}
            </>
          )}
          {tool === 'get_player' && (
            <label className="text-[10px] text-[#8a8f98]">玩家
              <input value={player} onChange={(e) => setPlayer(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
            </label>
          )}
          {tool === 'execute_command' && (
            <>
              <label className="text-[10px] text-[#8a8f98]">指令
                <input value={command} onChange={(e) => setCommand(e.target.value)} className="mt-1 w-full rounded-lg border border-white/[0.08] bg-black/30 px-2 py-1.5 text-[12px]" />
              </label>
              <label className="flex items-center gap-2 text-[11px] text-[#8a8f98]">
                <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                敏感操作已二次確認
              </label>
            </>
          )}
        </div>
        <button type="button" disabled={busy} onClick={() => void onCall()} className="mt-3 rounded-lg border border-[#64D2FF]/40 bg-[#64D2FF]/10 px-3 py-1.5 text-[12px] text-[#64D2FF] disabled:opacity-40">
          執行
        </button>
        {result && (
          <pre className="mt-3 overflow-auto rounded-lg bg-black/30 p-3 text-[11px] leading-relaxed text-[#AEAEB2]">
            {JSON.stringify(result, null, 2)}
          </pre>
        )}
      </section>

      <h3 className="mb-2 text-[11px] font-semibold text-[#8a8f98]">最近審計（{status?.recent?.length ?? 0}）</h3>
      <div className="space-y-2">
        {(status?.recent ?? []).length === 0 && <p className="py-6 text-center text-xs text-[#636366]">尚無 MCP 呼叫</p>}
        {(status?.recent ?? []).slice().reverse().map((row, index) => (
          <article key={`${row.ts}-${index}`} className="rounded-xl border border-white/[0.08] bg-[#1C1C1E] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12px] font-medium">{row.tool || row.remote}</span>
              <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">{row.ok ? 'ok' : 'fail'}</span>
              {row.dry_run && <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-[#8a8f98]">乾跑</span>}
              {row.duration_ms != null && <span className="text-[10px] text-[#8a8f98]">{row.duration_ms} ms</span>}
            </div>
            {row.error && <p className="mt-1 text-[11px] text-red-300">{row.error}</p>}
            <p className="mt-1 text-[10px] text-[#636366]">{row.ts}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
