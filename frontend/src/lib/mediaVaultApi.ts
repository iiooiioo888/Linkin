const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api';

function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export type MediaVaultAsset = {
  id: string;
  post_id: string;
  kind: string;
  relative_path: string;
  byte_size: number;
  width?: number | null;
  height?: number | null;
  mime: string;
  url?: string;
};

export type MediaVaultPost = {
  id: string;
  platform: string;
  source_url: string;
  author: string;
  batch_id: string;
  job_id: string;
  compliance_basis: string;
  crawl_method: string;
  media_type: string;
  caption?: string | null;
  summary?: string | null;
  dedup_hash: string;
  risk_level: string;
  created_at: string;
  ingested_at: string;
  thumb_url?: string | null;
  assets?: MediaVaultAsset[];
};

export type MediaVaultListResponse = {
  page: number;
  page_size: number;
  total: number;
  items: MediaVaultPost[];
};

export type MediaVaultMonitorSummary = {
  today_ingested: number;
  total_posts: number;
  success_rate: number | null;
  dedup_collision_rate: number;
  ingest_series_24h: Array<{ bucket: string; count: number }>;
  compliance_distribution: Array<{ label: string; count: number }>;
  storage_by_platform: Array<{ platform: string; bytes: number }>;
  ingest_errors: Array<{
    id: string;
    job_id: string;
    batch_id: string;
    level: string;
    message: string;
    created_at: string;
  }>;
  mediacrawler_failures: Array<{
    job_id: string;
    error: string;
    platform: string;
    finished_at?: number | null;
  }>;
  media_root: string;
};

export type MediaVaultFilters = {
  page?: number;
  page_size?: number;
  platform?: string[];
  batch_id?: string;
  compliance_basis?: string;
  media_type?: string;
  risk_level?: string;
  q?: string;
};

function buildQuery(filters: MediaVaultFilters): string {
  const params = new URLSearchParams();
  if (filters.page) params.set('page', String(filters.page));
  if (filters.page_size) params.set('page_size', String(filters.page_size));
  filters.platform?.forEach((p) => params.append('platform', p));
  if (filters.batch_id) params.set('batch_id', filters.batch_id);
  if (filters.compliance_basis) params.set('compliance_basis', filters.compliance_basis);
  if (filters.media_type) params.set('media_type', filters.media_type);
  if (filters.risk_level) params.set('risk_level', filters.risk_level);
  if (filters.q) params.set('q', filters.q);
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export function mediaVaultFileUrl(assetPath: string): string {
  if (assetPath.startsWith('http')) return assetPath;
  return apiUrl(assetPath.startsWith('/') ? assetPath : `/${assetPath}`);
}

export async function fetchMediaVaultImages(filters: MediaVaultFilters = {}): Promise<MediaVaultListResponse> {
  const resp = await fetch(apiUrl(`/media-vault/images${buildQuery(filters)}`));
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json() as Promise<MediaVaultListResponse>;
}

export async function fetchMediaVaultDetail(postId: string): Promise<MediaVaultPost> {
  const resp = await fetch(apiUrl(`/media-vault/images/${encodeURIComponent(postId)}`));
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json() as Promise<MediaVaultPost>;
}

export async function fetchMediaVaultMonitorSummary(): Promise<MediaVaultMonitorSummary> {
  const resp = await fetch(apiUrl('/media-vault/monitor/summary'));
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json() as Promise<MediaVaultMonitorSummary>;
}
