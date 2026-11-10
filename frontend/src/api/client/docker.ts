/**
 * EvoLoop 後端 API 客戶端 — Docker 容器管理、臨時容器任務與宿主資源。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { DockerActionResult, DockerBudget, DockerStatus } from '../../types';
import type { TaskWsMessage } from './tasks';
import { attachGateHeaders } from '../../lib/auth';
import { apiUrl, wsUrl } from './http';

// ==================== Docker 容器管理 ====================

/** 獲取 Docker 狀態摘要（容器列表 + 健康檢查）。 */
export async function fetchDockerStatus(): Promise<DockerStatus> {
  const resp = await fetch(apiUrl('/docker/status'));
  if (!resp.ok) throw new Error(`讀取 Docker 狀態失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取 Docker 容器預算狀態（公司全權控制）。 */
export async function fetchDockerBudget(): Promise<DockerBudget> {
  const resp = await fetch(apiUrl('/docker/budget'));
  if (!resp.ok) throw new Error(`讀取 Docker 預算失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export interface HostResourceSample {
  available: boolean;
  cpu_percent?: number;
  mem_percent?: number;
  net_percent?: number | null;
  net_link_assumed?: boolean;
  error?: string;
}

/** 主機 CPU／記憶體／網路吞吐。 */
export async function fetchHostResources(): Promise<HostResourceSample> {
  const resp = await fetch(apiUrl('/system/resources'));
  if (!resp.ok) throw new Error(`讀取主機資源失敗（HTTP ${resp.status}）`);
  return resp.json() as Promise<HostResourceSample>;
}

/** 獲取容器資源使用統計。 */
export async function fetchDockerStats(): Promise<{ stats: Record<string, import('../../types').DockerContainerStats> }> {
  const resp = await fetch(apiUrl('/docker/stats'));
  if (!resp.ok) throw new Error(`讀取 Docker 統計失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 獲取指定服務日誌。 */
export async function fetchDockerLogs(service: string, tail: number = 100): Promise<{ service: string; tail: number; logs: string }> {
  const resp = await fetch(apiUrl(`/docker/logs/${encodeURIComponent(service)}?tail=${tail}`));
  if (!resp.ok) throw new Error(`讀取日誌失敗（HTTP ${resp.status}）`);
  return resp.json();
}

// ==================== 臨時容器任務 ====================

export interface ContainerTaskCreateBody {
  image: string;
  command: string[];
  timeout_sec?: number;
  cpu?: number;
  memory_mb?: number;
  network?: boolean;
  env?: Record<string, string>;
  workdir?: string;
}

export interface ContainerTaskPublic {
  task_id: string;
  status: string;
  image: string;
  command: string[];
  exit_code?: number | null;
  error?: string;
  logs_tail?: string;
}

export async function fetchContainerConfig(): Promise<{ enabled: boolean; allowlist: string[] }> {
  const resp = await fetch(apiUrl('/linkin/containers/config'), attachGateHeaders());
  if (!resp.ok) throw new Error(`讀取容器配置失敗（HTTP ${resp.status}）`);
  return resp.json();
}

export async function createContainerTask(body: ContainerTaskCreateBody): Promise<{ task_id: string; status: string }> {
  const resp = await fetch(
    apiUrl('/linkin/containers/tasks'),
    attachGateHeaders({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  );
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(detail || `提交容器任務失敗（HTTP ${resp.status}）`);
  }
  return resp.json();
}

export async function fetchContainerTask(taskId: string): Promise<ContainerTaskPublic> {
  const resp = await fetch(
    apiUrl(`/linkin/containers/tasks/${encodeURIComponent(taskId)}`),
    attachGateHeaders(),
  );
  if (!resp.ok) throw new Error(`讀取容器任務失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 臨時容器任務 WebSocket（日誌 + finished）。 */
export class ContainerTaskWebSocket {
  private ws: WebSocket | null = null;
  private taskId: string;
  private onMessage: (msg: TaskWsMessage) => void;

  constructor(taskId: string, onMessage: (msg: TaskWsMessage) => void) {
    this.taskId = taskId;
    this.onMessage = onMessage;
  }

  connect(): void {
    this.ws = new WebSocket(wsUrl(`/linkin/containers/tasks/${encodeURIComponent(this.taskId)}/ws`));
    this.ws.onmessage = (event) => {
      try {
        this.onMessage(JSON.parse(event.data) as TaskWsMessage);
      } catch {
        /* ignore */
      }
    };
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
  }
}

/** 重啟指定服務。 */
export async function restartDockerService(service: string): Promise<DockerActionResult> {
  const resp = await fetch(apiUrl(`/docker/restart/${encodeURIComponent(service)}`), { method: 'POST' });
  if (!resp.ok) throw new Error(`重啟失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 停止指定服務。 */
export async function stopDockerService(service: string): Promise<DockerActionResult> {
  const resp = await fetch(apiUrl(`/docker/stop/${encodeURIComponent(service)}`), { method: 'POST' });
  if (!resp.ok) throw new Error(`停止失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 啟動指定服務。 */
export async function startDockerService(service: string): Promise<DockerActionResult> {
  const resp = await fetch(apiUrl(`/docker/start/${encodeURIComponent(service)}`), { method: 'POST' });
  if (!resp.ok) throw new Error(`啟動失敗（HTTP ${resp.status}）`);
  return resp.json();
}
