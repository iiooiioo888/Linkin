/**
 * 外部整合 API（MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil）。
 *
 * 契約：啟用與動作皆為顯式；未啟用時後端 fail-closed（不發網路請求）。
 */
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export type IntegrationGroup = 'recall' | 'agent' | 'design';

export interface IntegrationStatus {
  name: string;
  display_name: string;
  role: string;
  group: IntegrationGroup | string;
  summary: string;
  docs_url: string;
  enabled: boolean;
  base_url: string;
  health?: {
    ok?: boolean;
    enabled?: boolean;
    reason_code?: string;
    latency_ms?: number;
    error_code?: string;
  };
}

export interface IntegrationCatalogEntry {
  name: string;
  display_name: string;
  role: string;
  group: IntegrationGroup | string;
  summary: string;
  default_url: string;
  env_enabled: string;
  env_url: string;
  docs_url: string;
}

export interface RecallResult {
  injection: string;
  fragments: unknown[];
  history: unknown[];
  reason_codes: string[];
  degraded_sources: string[];
  token_report: Record<string, unknown>;
}

export interface ActionResult {
  ok: boolean;
  data?: unknown;
  error_code?: string;
  reason_code?: string;
  name?: string;
  enabled?: boolean;
  allowed?: boolean;
  forced?: boolean;
  ambiguity?: number;
  passed?: boolean;
  stages?: unknown[];
  failed_stage?: string;
  result?: unknown;
}

async function readJson<T>(resp: Response, fallback: string): Promise<T> {
  if (!resp.ok) throw new Error(`${fallback}（HTTP ${resp.status}）`);
  return resp.json() as Promise<T>;
}

export async function fetchIntegrations(): Promise<IntegrationStatus[]> {
  const resp = await fetch(apiUrl('/integrations'));
  const data = await readJson<{ integrations: IntegrationStatus[] }>(resp, '讀取整合目錄失敗');
  return data.integrations ?? [];
}

export async function fetchIntegrationCatalog(): Promise<IntegrationCatalogEntry[]> {
  const resp = await fetch(apiUrl('/integrations/catalog'));
  const data = await readJson<{ catalog: IntegrationCatalogEntry[] }>(resp, '讀取整合目錄失敗');
  return data.catalog ?? [];
}

export async function toggleIntegration(name: string, enabled: boolean): Promise<ActionResult> {
  const resp = await fetch(apiUrl(`/integrations/${encodeURIComponent(name)}/toggle`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  return readJson(resp, '切換整合失敗');
}

export async function runIntegrationRecall(body: {
  query: string;
  history?: Array<{ role: string; content: string }>;
  user_id?: string;
  cube_ids?: string[];
  knowledge_base_id?: string;
  audit_path?: boolean;
}): Promise<RecallResult> {
  const resp = await fetch(apiUrl('/integrations/recall'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(resp, '召回失敗');
}

export async function yaoListWorkspaces(): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/yao/workspaces'));
  return readJson(resp, '讀取 Yao 工作區失敗');
}

export async function yaoListTasks(workspaceId: string, status = ''): Promise<ActionResult> {
  const q = status ? `?status=${encodeURIComponent(status)}` : '';
  const resp = await fetch(
    apiUrl(`/integrations/yao/workspaces/${encodeURIComponent(workspaceId)}/tasks${q}`),
  );
  return readJson(resp, '讀取 Yao 任務失敗');
}

export async function yaoCreateTask(body: {
  workspace_id: string;
  title: string;
  prompt: string;
  agent_id?: string;
}): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/yao/tasks'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(resp, '建立 Yao 任務失敗');
}

export async function ouroborosInterview(goal: string, context = ''): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/ouroboros/interview'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ goal, context }),
  });
  return readJson(resp, 'Ouroboros 訪談失敗');
}

export async function ouroborosAuto(body: {
  goal: string;
  ambiguity: number;
  force?: boolean;
}): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/ouroboros/auto'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(resp, 'Ouroboros auto 失敗');
}

export async function ouroborosEvaluate(executionId: string): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/ouroboros/evaluate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ execution_id: executionId }),
  });
  return readJson(resp, 'Ouroboros 評估失敗');
}

export async function openpencilListProjects(): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/openpencil/projects'));
  return readJson(resp, '讀取 OpenPencil 專案失敗');
}

export async function openpencilGenerate(body: {
  prompt: string;
  project_id?: string;
  style?: string;
}): Promise<ActionResult> {
  const resp = await fetch(apiUrl('/integrations/openpencil/generate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return readJson(resp, 'OpenPencil 生成失敗');
}
