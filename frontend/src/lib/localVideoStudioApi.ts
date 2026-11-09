const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function parseJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail || `HTTP ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export type LvsProject = {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  created_at: string;
  shot_count: number;
};

export type LvsShot = {
  id: string;
  project_id: string;
  scene_no: number;
  shot_no: number;
  description: string;
  dialogue?: string | null;
  duration_sec: number;
  status: string;
  selected_keyframe_asset_id?: string | null;
  selected_clip_asset_id?: string | null;
  created_at: string;
};

export type LvsAsset = {
  id: string;
  project_id: string;
  shot_id?: string | null;
  type: string;
  relative_path: string;
  mime?: string | null;
  bytes?: number | null;
  sha256?: string | null;
  created_at: string;
};

export type LvsScript = {
  id: string;
  project_id: string;
  content_json: Record<string, unknown>;
  version: number;
  created_at: string;
  imported_shots: number;
};

const PROJECT_KEY = 'lvs-selected-project-id';

export function rememberLvsProjectId(id: string): void {
  sessionStorage.setItem(PROJECT_KEY, id);
}

export function recalledLvsProjectId(): string | null {
  return sessionStorage.getItem(PROJECT_KEY);
}

export async function listLvsProjects(): Promise<LvsProject[]> {
  const resp = await fetch(apiUrl('/local-video-studio/api/v1/projects'));
  return parseJson(resp);
}

export async function createLvsProject(body: {
  name: string;
  description?: string;
}): Promise<LvsProject> {
  const resp = await fetch(apiUrl('/local-video-studio/api/v1/projects'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJson(resp);
}

export async function getLvsProject(id: string): Promise<LvsProject> {
  const resp = await fetch(apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(id)}`));
  return parseJson(resp);
}

export async function listLvsShots(projectId: string): Promise<LvsShot[]> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/shots`),
  );
  return parseJson(resp);
}

export async function createLvsShot(
  projectId: string,
  body: {
    scene_no: number;
    shot_no: number;
    description: string;
    dialogue?: string;
    duration_sec?: number;
  },
): Promise<LvsShot> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/shots`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  return parseJson(resp);
}

export async function uploadLvsScript(
  projectId: string,
  content_json: Record<string, unknown>,
): Promise<LvsScript> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/scripts`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_json }),
    },
  );
  return parseJson(resp);
}

export type LvsJob = {
  id: string;
  project_id: string;
  shot_id: string;
  job_type: string;
  workflow_template: string;
  params_json: Record<string, unknown>;
  status: string;
  attempt: number;
  max_attempts: number;
  priority: number;
  assigned_agent?: string | null;
  error?: string | null;
  created_at: string;
  asset?: {
    id: string;
    type: string;
    relative_path: string;
    bytes?: number | null;
    sha256?: string | null;
  } | null;
};

export async function listLvsJobs(projectId?: string): Promise<LvsJob[]> {
  const q = projectId ? `?project_id=${encodeURIComponent(projectId)}` : '';
  const resp = await fetch(apiUrl(`/local-video-studio/api/v1/jobs${q}`));
  return parseJson(resp);
}

export async function createLvsJob(body: {
  project_id: string;
  shot_id: string;
  job_type: string;
  workflow_template: string;
  params?: Record<string, unknown>;
}): Promise<LvsJob> {
  const resp = await fetch(apiUrl('/local-video-studio/api/v1/jobs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return parseJson(resp);
}

export type LvsReviewQueueItem = {
  asset_id: string;
  project_id: string;
  shot_id?: string | null;
  asset_type: string;
  relative_path: string;
  shot_status?: string | null;
  last_decision?: string | null;
};

export async function listLvsReviewQueue(projectId: string): Promise<LvsReviewQueueItem[]> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/review-queue`),
  );
  return parseJson(resp);
}

export async function reviewLvsAsset(
  assetId: string,
  body: { decision: 'approve' | 'reject' | 'needs_retry'; reason?: string },
): Promise<unknown> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/assets/${encodeURIComponent(assetId)}/review`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  return parseJson(resp);
}

export async function composeLvsProject(
  projectId: string,
  body: { shot_ids: string[]; output_name?: string; add_watermark?: boolean },
): Promise<{ relative_path: string; compliance_id: string; engine: string }> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/compose`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  return parseJson(resp);
}

export type LvsResourceSummary = {
  project_id: string;
  gpu_minutes: number;
  wall_minutes: number;
  attempts: number;
  discarded_count: number;
  storage_bytes: number;
  api_calls: number;
  job_count: number;
  asset_count: number;
};

export async function getLvsResources(projectId: string): Promise<LvsResourceSummary> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/resources`),
  );
  return parseJson(resp);
}

export async function listLvsAssets(projectId: string, type?: string): Promise<LvsAsset[]> {
  const q = type ? `?type=${encodeURIComponent(type)}` : '';
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/assets${q}`),
  );
  return parseJson(resp);
}

export function lvsAssetMediaUrl(assetId: string): string {
  return apiUrl(`/local-video-studio/api/v1/assets/${encodeURIComponent(assetId)}/media`);
}

export async function cancelLvsJob(jobId: string): Promise<LvsJob> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/jobs/${encodeURIComponent(jobId)}/cancel`),
    { method: 'POST' },
  );
  return parseJson(resp);
}

export async function retryLvsJob(jobId: string): Promise<LvsJob> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/jobs/${encodeURIComponent(jobId)}/retry`),
    { method: 'POST' },
  );
  return parseJson(resp);
}

export async function getLvsCompliance(assetId: string): Promise<{
  id: string;
  asset_id: string;
  explicit_mark: boolean;
  metadata_json: Record<string, unknown>;
  watermark_id?: string | null;
  created_at: string;
}> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/assets/${encodeURIComponent(assetId)}/compliance`),
  );
  return parseJson(resp);
}

export async function uploadLvsFile(
  projectId: string,
  kind: 'audio' | 'subtitle' | 'ref',
  file: File,
): Promise<{ relative_path: string; bytes: number; kind: string; filename: string }> {
  const body = new FormData();
  body.append('file', file);
  const resp = await fetch(
    apiUrl(
      `/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/uploads?kind=${encodeURIComponent(kind)}`,
    ),
    { method: 'POST', body },
  );
  return parseJson(resp);
}

export async function composeLvsProjectFull(
  projectId: string,
  body: {
    shot_ids: string[];
    output_name?: string;
    add_watermark?: boolean;
    metadata?: Record<string, unknown>;
  },
): Promise<{
  relative_path: string;
  compliance_id: string;
  engine: string;
  asset: LvsAsset;
}> {
  const resp = await fetch(
    apiUrl(`/local-video-studio/api/v1/projects/${encodeURIComponent(projectId)}/compose`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  return parseJson(resp);
}
