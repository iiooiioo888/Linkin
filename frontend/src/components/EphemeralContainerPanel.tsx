/**
 * 實驗室 · 臨時容器：提交隔離 Docker 任務並 WebSocket 串流日誌。
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ContainerTaskWebSocket,
  createContainerTask,
  fetchContainerConfig,
  fetchContainerTask,
  type ContainerTaskPublic,
  type TaskWsMessage,
} from '../api/client';
import ErrorState from './ui/ErrorState';

const DEFAULT_IMAGE = 'python:3.12-slim';

export default function EphemeralContainerPanel() {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [allowlist, setAllowlist] = useState<string[]>([]);
  const [image, setImage] = useState(DEFAULT_IMAGE);
  const [command, setCommand] = useState('python -c "print(42)"');
  const [timeoutSec, setTimeoutSec] = useState(120);
  const [network, setNetwork] = useState(false);
  const [taskId, setTaskId] = useState('');
  const [status, setStatus] = useState('');
  const [logs, setLogs] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLPreElement>(null);
  const wsRef = useRef<ContainerTaskWebSocket | null>(null);

  useEffect(() => {
    fetchContainerConfig()
      .then((cfg) => {
        setEnabled(cfg.enabled);
        setAllowlist(cfg.allowlist ?? []);
        if (cfg.allowlist?.length && !cfg.allowlist.includes(image)) {
          setImage(cfg.allowlist[0]);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  const onWsMessage = useCallback((msg: TaskWsMessage) => {
    if (msg.event === 'log' && typeof msg.data.chunk === 'string') {
      setLogs((prev) => prev + msg.data.chunk);
    }
    if (msg.event === 'snapshot' && msg.data.status) {
      setStatus(String(msg.data.status));
    }
    if (msg.event === 'finished') {
      setStatus(String(msg.data.status ?? ''));
      if (msg.data.error) setError(String(msg.data.error));
      const snap = msg.data.snapshot as ContainerTaskPublic | undefined;
      if (snap?.exit_code !== undefined && snap?.exit_code !== null) {
        setStatus(`${snap.status} (exit ${snap.exit_code})`);
      }
    }
  }, []);

  const connectWs = useCallback(
    (id: string) => {
      wsRef.current?.close();
      const ws = new ContainerTaskWebSocket(id, onWsMessage);
      ws.connect();
      wsRef.current = ws;
    },
    [onWsMessage],
  );

  useEffect(() => () => wsRef.current?.close(), []);

  const parseCommand = (raw: string): string[] => {
    const trimmed = raw.trim();
    if (!trimmed) return [];
    if (trimmed.startsWith('[')) {
      try {
        const arr = JSON.parse(trimmed) as unknown;
        if (Array.isArray(arr)) return arr.map(String);
      } catch {
        /* fall through */
      }
    }
    return trimmed.split(/\s+/);
  };

  const handleSubmit = async () => {
    setError('');
    setLogs('');
    setBusy(true);
    try {
      const cmd = parseCommand(command);
      if (!cmd.length) {
        setError('請輸入命令');
        return;
      }
      const { task_id } = await createContainerTask({
        image,
        command: cmd,
        timeout_sec: timeoutSec,
        network,
      });
      setTaskId(task_id);
      setStatus('queued');
      connectWs(task_id);
      const poll = window.setInterval(async () => {
        try {
          const t = await fetchContainerTask(task_id);
          setStatus(t.status);
          if (t.status === 'succeeded' || t.status === 'failed' || t.status === 'timed_out') {
            window.clearInterval(poll);
            setBusy(false);
          }
        } catch {
          window.clearInterval(poll);
          setBusy(false);
        }
      }, 1500);
    } catch (e) {
      setError(String(e));
      setBusy(false);
    }
  };

  if (enabled === false) {
    return (
      <ErrorState
        kind="generic"
        message="臨時容器未啟用：後端請設定 EVOL_EPHEMERAL_CONTAINERS=1 並確保 Docker 可用。"
      />
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,360px)_1fr]">
      <section className="apple-card apple-card--pad flex flex-col gap-3">
        <h2 className="apple-title">隔離容器任務</h2>
        <p className="text-[11px] text-[#8E8E93]">
          非 root · 唯讀根檔案系統 · 預設無網路 · 逾時自動終止並刪除容器。
        </p>
        <label className="text-[11px] text-[#8E8E93]">
          映像（白名單）
          <select
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-[13px]"
            value={image}
            onChange={(e) => setImage(e.target.value)}
          >
            {(allowlist.length ? allowlist : [DEFAULT_IMAGE]).map((img) => (
              <option key={img} value={img}>{img}</option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-[#8E8E93]">
          命令（shell 或 JSON 陣列）
          <textarea
            className="mt-1 w-full min-h-[72px] rounded-lg border border-white/10 bg-black/30 px-2 py-2 font-mono text-[12px]"
            value={command}
            onChange={(e) => setCommand(e.target.value)}
          />
        </label>
        <label className="text-[11px] text-[#8E8E93]">
          逾時（秒）
          <input
            type="number"
            min={5}
            max={600}
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2 py-2 text-[13px]"
            value={timeoutSec}
            onChange={(e) => setTimeoutSec(Number(e.target.value))}
          />
        </label>
        <label className="flex items-center gap-2 text-[12px] text-[#AEAEB2]">
          <input
            type="checkbox"
            checked={network}
            onChange={(e) => setNetwork(e.target.checked)}
            className="accent-[#007AFF]"
          />
          允許網路（預設關閉）
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleSubmit()}
          className="rounded-full bg-[#007AFF] px-4 py-2 text-[13px] font-bold text-white disabled:opacity-50"
        >
          {busy ? '執行中…' : '提交任務'}
        </button>
        {taskId && (
          <p className="font-mono text-[11px] text-[#8E8E93]">task: {taskId}</p>
        )}
        {status && <p className="text-[12px] text-[#34C759]">狀態：{status}</p>}
        {error && <p className="text-[12px] text-[#FF3B30]">{error}</p>}
      </section>
      <section className="apple-card flex min-h-[320px] flex-col">
        <div className="apple-card__head">
          <h2 className="apple-title">日誌串流</h2>
        </div>
        <pre
          ref={logRef}
          className="flex-1 overflow-auto p-4 font-mono text-[11px] leading-relaxed text-[#D1D1D6]"
        >
          {logs || '（等待輸出）'}
        </pre>
      </section>
    </div>
  );
}
