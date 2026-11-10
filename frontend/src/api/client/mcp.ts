/**
 * EvoLoop 後端 API 客戶端 — MCP 連線管理 API。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import { apiUrl, readApiError } from './http';

// ═══════════════════════════════════════════════════════════
// MCP 連線管理 API
// ═══════════════════════════════════════════════════════════

export interface McpServerRecord {
  id: string;
  name: string;
  transport: 'stdio' | 'sse' | 'http';
  command: string;
  env: Record<string, string>;
  url: string;
  headers: Record<string, string>;
  enabled: boolean;
  allowed_tools: string[];
  readonly: boolean;
  timeout: number;
  created_at: string;
  updated_at: string;
  last_probe: McpProbeResult | Record<string, never>;
}

export interface McpProbeResult {
  ok: boolean;
  tool_count: number;
  tools: string[];
  latency_ms: number;
  probed_at: string;
  error: string;
}

export interface McpServerSaveBody {
  id?: string | null;
  name: string;
  transport: 'stdio' | 'sse' | 'http';
  command?: string;
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  enabled?: boolean;
  allowed_tools?: string[];
  readonly?: boolean;
  timeout?: number;
}

export async function fetchMcpServers(): Promise<McpServerRecord[]> {
  const resp = await fetch(apiUrl('/mcp/servers'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { servers: McpServerRecord[] };
  return data.servers ?? [];
}

export async function saveMcpServer(body: McpServerSaveBody): Promise<McpServerRecord> {
  const resp = await fetch(apiUrl('/mcp/servers'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { server: McpServerRecord };
  return data.server;
}

export async function toggleMcpServer(id: string): Promise<McpServerRecord> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}/toggle`), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { server: McpServerRecord };
  return data.server;
}

export async function deleteMcpServer(id: string): Promise<void> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}`), { method: 'DELETE' });
  if (!resp.ok) throw new Error(await readApiError(resp));
}

export async function probeMcpServer(id: string): Promise<McpProbeResult> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}/probe`), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function callMcpTool(id: string, tool: string, args: Record<string, unknown>): Promise<string> {
  const resp = await fetch(apiUrl(`/mcp/servers/${encodeURIComponent(id)}/call`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool, args }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { result: string };
  return data.result;
}

export async function mountMcpTools(): Promise<{ mounted: string[]; count: number }> {
  const resp = await fetch(apiUrl('/mcp/mount'), { method: 'POST' });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}
