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
