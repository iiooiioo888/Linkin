/**
 * EvoLoop 後端 API 客戶端 — MediaCrawler 多平台採集整合。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import { apiUrl, readApiError } from './http';

/** MediaCrawler 多平台採集整合 */
export interface MediaCrawlerStatus {
  enabled: boolean;
  dry_run: boolean;
  tier: 'enabled' | 'available' | 'needsKey';
  installation: { installed: boolean; reason?: string; home?: string; runner?: string };
  results_root: string;
  max_concurrent_jobs: number;
  cookie_configured: boolean;
  cookie_preview: string;
  platforms: string[];
  crawl_types: string[];
  login_types: string[];
  legal_notice: string;
  running_jobs?: number;
  recent_jobs?: MediaCrawlerJobRecord[];
}

export interface MediaCrawlerJobRecord {
  job_id: string;
  status: string;
  request: Record<string, unknown>;
  created_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  error?: string;
  dry_run?: boolean;
  duration_seconds?: number | null;
  log_tail?: string;
  results?: Array<{ name: string; size: number }>;
}

export interface MediaCrawlerJobBody {
  platform: string;
  crawl_type: string;
  login_type?: string;
  keywords?: string;
  post_ids?: string;
  creator_ids?: string;
  enable_comments?: boolean;
  save_format?: string;
  max_notes?: number;
  dry_run?: boolean;
  cookie?: string;
}

export async function fetchMediaCrawlerStatus(): Promise<MediaCrawlerStatus> {
  const resp = await fetch(apiUrl('/mediacrawler/status'));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function updateMediaCrawlerConfig(cookie: string): Promise<{ cookie_configured: boolean; cookie_preview: string }> {
  const resp = await fetch(apiUrl('/mediacrawler/config'), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cookie }),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function validateMediaCrawlerJob(body: MediaCrawlerJobBody): Promise<{ valid: boolean; errors: string[]; command?: string[] }> {
  const resp = await fetch(apiUrl('/mediacrawler/jobs/validate'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function startMediaCrawlerJob(body: MediaCrawlerJobBody): Promise<MediaCrawlerJobRecord> {
  const resp = await fetch(apiUrl('/mediacrawler/jobs'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export async function fetchMediaCrawlerJobs(limit = 20): Promise<MediaCrawlerJobRecord[]> {
  const resp = await fetch(apiUrl(`/mediacrawler/jobs?limit=${limit}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  const data = (await resp.json()) as { jobs: MediaCrawlerJobRecord[] };
  return data.jobs ?? [];
}

export async function fetchMediaCrawlerJob(jobId: string): Promise<MediaCrawlerJobRecord> {
  const resp = await fetch(apiUrl(`/mediacrawler/jobs/${jobId}`));
  if (!resp.ok) throw new Error(await readApiError(resp));
  return resp.json();
}

export function mediaCrawlerResultUrl(jobId: string, filename: string): string {
  return apiUrl(`/mediacrawler/jobs/${encodeURIComponent(jobId)}/results/${encodeURIComponent(filename)}`);
}
