/**
 * EvoLoop 後端 API 客戶端 — 任務介面、任務 WebSocket 與監控 Hub WebSocket。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { CheckpointSummary, SeatFeedQuery, SeatIOFeed, SeatIORecord, TaskOptions, TaskProgress, TraceEntry, TraceSummary } from '../../types';
import { attachGateHeaders } from '../../lib/auth';
import { apiUrl, wsUrl, parseBillingError } from './http';

// ==================== 任務介面 ====================

/** 建立後台任務（統一模式），回傳 task_id。 */
export async function createTask(
  query: string,
  executionStrategy: 'auto' | 'simple' | 'company' = 'auto',
  companyTemplate: string = 'quick_task',
  options?: TaskOptions,
): Promise<{ task_id: string; strategy: string }> {
  let resp: Response;
  try {
    resp = await fetch(
      apiUrl('/tasks'),
      attachGateHeaders({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          execution_strategy: executionStrategy,
          company_template: companyTemplate,
          options: options ?? {},
        }),
      }),
    );
  } catch {
    throw new Error('網路連線失敗，請檢查後端服務是否啟動');
  }
  if (!resp.ok) throw new Error(await parseBillingError(resp));
  return resp.json();
}

/** 斷點續跑：從檢查點恢復任務執行。 */
export async function resumeTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/resume`), {
    method: 'POST',
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? `恢復失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

/** 獲取任務的思考過程記錄（分頁 + 可篩選；event/role 逗號分隔多值）。 */
export async function fetchTaskTrace(
  taskId: string,
  limit: number = 100,
  offset: number = 0,
  filters?: { event?: string; role?: string; itemId?: string; withCounts?: boolean },
): Promise<{
  task_id: string;
  offset: number;
  limit: number;
  events: TraceEntry[];
  event_counts?: Record<string, number>;
}> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (filters?.event) params.set('event', filters.event);
  if (filters?.role) params.set('role', filters.role);
  if (filters?.itemId) params.set('item_id', filters.itemId);
  if (filters?.withCounts) params.set('with_counts', 'true');
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/trace?${params}`));
  if (!resp.ok) throw new Error(`讀取軌跡失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取任務的檢查點信息。 */
export async function fetchTaskCheckpoint(taskId: string): Promise<{
  task_id: string;
  exists: boolean;
  checkpoint?: Record<string, unknown>;
}> {
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/checkpoint`));
  if (!resp.ok) throw new Error(`讀取檢查點失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 列出所有思考過程軌跡檔案摘要。 */
export async function fetchTraces(limit: number = 80): Promise<{ traces: TraceSummary[] }> {
  const resp = await fetch(apiUrl(`/traces?limit=${limit}`));
  if (!resp.ok) throw new Error(`讀取軌跡列表失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 列出所有可恢復的檢查點。 */
export async function fetchCheckpoints(): Promise<{ checkpoints: CheckpointSummary[] }> {
  const resp = await fetch(apiUrl('/checkpoints'));
  if (!resp.ok) throw new Error(`讀取檢查點列表失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 查詢任務進度。eventsLimit=0 表示向後端索取全部事件（預設 50）。 */
export async function fetchTask(taskId: string, eventsLimit?: number): Promise<TaskProgress> {
  const q = eventsLimit === undefined ? '' : `?events_limit=${eventsLimit}`;
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}${q}`));
  if (!resp.ok) throw new Error(`查詢任務失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 席位投遞餵給（公司模式監察頁資料源）。 */
export async function fetchSeatFeed(params: SeatFeedQuery = {}): Promise<SeatIOFeed> {
  const q = new URLSearchParams();
  if (params.task_id) q.set('task_id', params.task_id);
  if (params.run_id) q.set('run_id', params.run_id);
  if (params.role) q.set('role', params.role);
  if (params.layer !== undefined) q.set('layer', String(params.layer));
  if (params.item_id) q.set('item_id', params.item_id);
  if (params.kind) q.set('kind', params.kind);
  q.set('limit', String(params.limit ?? 120));
  if (params.full) q.set('full', 'true');
  const resp = await fetch(apiUrl(`/monitor/raho/feed?${q.toString()}`));
  if (!resp.ok) throw new Error(`讀取席位投遞失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 單次席位投遞全文（系統提示詞／prompt／回應／來源分解）。 */
export async function fetchSeatDetail(ioId: string): Promise<SeatIORecord> {
  const resp = await fetch(apiUrl(`/monitor/raho/seat/${encodeURIComponent(ioId)}`));
  if (!resp.ok) throw new Error(`讀取投遞全文失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 請求取消執行中的任務。 */
export async function cancelTask(taskId: string): Promise<{ success: boolean; message: string }> {
  const resp = await fetch(apiUrl(`/tasks/${encodeURIComponent(taskId)}/cancel`), {
    method: 'POST',
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? `取消失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

// ==================== 任務 WebSocket 實時推送 ====================

/** WebSocket 事件消息格式。 */
export interface TaskWsMessage {
  task_id: string;
  event: string;
  data: Record<string, unknown>;
}

/**
 * 任務 WebSocket 客戶端。
 *
 * 連接後自動接收任務進度推送，支援：
 * - onMessage: 事件回調
 * - 自動重連（可選）
 * - 心跳保持連接
 */
export class TaskWebSocket {
  private ws: WebSocket | null = null;
  private taskId: string;
  private onMessage: (msg: TaskWsMessage) => void;
  private onClose?: () => void;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private shouldReconnect = true;

  constructor(
    taskId: string,
    onMessage: (msg: TaskWsMessage) => void,
    onClose?: () => void,
  ) {
    this.taskId = taskId;
    this.onMessage = onMessage;
    this.onClose = onClose;
  }

  /** 建立 WebSocket 連接。 */
  connect(): void {
    try {
      this.ws = new WebSocket(wsUrl(`/tasks/${encodeURIComponent(this.taskId)}/ws`));
    } catch {
      // WebSocket 不可用時降級為輪詢
      this.onClose?.();
      return;
    }

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as TaskWsMessage;
        this.onMessage(msg);
      } catch {
        // 忽略解析失敗的消息
      }
    };

    this.ws.onclose = () => {
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
      } else {
        this.onClose?.();
      }
    };

    this.ws.onerror = () => {
      // 錯誤時關閉連接（觸發重連或降級）
      this.ws?.close();
    };
  }

  /** 發送心跳。 */
  ping(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping');
    }
  }

  /** 關閉連接（不再重連）。 */
  close(): void {
    this.shouldReconnect = false;
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('close');
    }
    this.ws?.close();
  }

  /** 連接是否已建立。 */
  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

/** 監控中心 Hub WebSocket：週期推送彙總快照。 */
export class MonitorHubWebSocket {
  private ws: WebSocket | null = null;
  private onSnapshot: (snap: Record<string, unknown>) => void;
  private onClose?: () => void;
  private heartbeat: ReturnType<typeof setInterval> | null = null;

  constructor(
    onSnapshot: (snap: Record<string, unknown>) => void,
    onClose?: () => void,
  ) {
    this.onSnapshot = onSnapshot;
    this.onClose = onClose;
  }

  connect(): void {
    try {
      this.ws = new WebSocket(wsUrl('/monitor/ws'));
    } catch {
      this.onClose?.();
      return;
    }

    this.ws.onopen = () => {
      this.heartbeat = setInterval(() => this.ping(), 15000);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as {
          event?: string;
          data?: Record<string, unknown>;
        };
        if (msg.event === 'snapshot' && msg.data) {
          this.onSnapshot(msg.data);
        } else if (msg.event !== 'pong') {
          this.onSnapshot(msg as Record<string, unknown>);
        }
      } catch {
        // ignore
      }
    };

    this.ws.onclose = () => {
      if (this.heartbeat) {
        clearInterval(this.heartbeat);
        this.heartbeat = null;
      }
      this.onClose?.();
    };

    this.ws.onerror = () => {
      this.ws?.close();
    };
  }

  ping(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('ping');
    }
  }

  close(): void {
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send('close');
    }
    this.ws?.close();
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
