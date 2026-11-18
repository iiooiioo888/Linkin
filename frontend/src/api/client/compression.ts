/**
 * 規則壓縮 API。只打既有函式的薄路由，不呼叫提示詞優化。
 */
import { apiUrl } from './http';

export const COMPRESS_LIMIT = { min: 17, max: 20_000, fallback: 720 } as const;
export const DECISION_LIMIT = { min: 1, max: 50, fallback: 5 } as const;
export const SUMMARY_LIMIT = { min: 17, max: 20_000, fallback: 280 } as const;
export const TRUNCATE_LIMIT = { min: 1, max: 100_000 } as const;
export const TEXT_CAP = 200_000;

export interface CompressContextResult {
  text: string;
  original_chars: number;
  result_chars: number;
  helper: string;
}

export interface ExtractDecisionsResult {
  decisions: string[];
  helper: string;
}

export interface SummarizeTraceResult {
  summary: string;
  helper: string;
}

export interface TruncatePromptResult {
  text: string;
  original_chars: number;
  result_chars: number;
  helper: string;
}

export function readWholeNumber(raw: string): { ok: true; value: number | undefined } | { ok: false } {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, value: undefined };
  if (!/^\d+$/.test(trimmed)) return { ok: false };
  const value = Number(trimmed);
  if (!Number.isSafeInteger(value)) return { ok: false };
  return { ok: true, value };
}

export function boundedLimit(
  raw: string,
  range: { min: number; max: number },
): { ok: true; value: number | undefined } | { ok: false; message: string } {
  const parsed = readWholeNumber(raw);
  if (!parsed.ok) return { ok: false, message: '上限要是整數。' };
  if (parsed.value !== undefined && (parsed.value < range.min || parsed.value > range.max)) {
    return { ok: false, message: `上限要在 ${range.min} 到 ${range.max} 之間。` };
  }
  return { ok: true, value: parsed.value };
}

async function compressionError(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail;
  } catch {
    /* 非 JSON */
  }
  return `壓縮沒有完成（HTTP ${resp.status}）`;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await compressionError(resp));
  return (await resp.json()) as T;
}

export function compressContext(text: string, limit?: number): Promise<CompressContextResult> {
  return postJson('/context/compress', limit === undefined ? { text } : { text, limit });
}

export function extractContextDecisions(text: string, limit?: number): Promise<ExtractDecisionsResult> {
  return postJson('/context/decisions', limit === undefined ? { text } : { text, limit });
}

export function summarizeContextTrace(input: {
  title: string;
  body: string;
  failureReason: string;
  limit?: number;
}): Promise<SummarizeTraceResult> {
  const payload: {
    title: string;
    body: string;
    failure_reason: string;
    limit?: number;
  } = {
    title: input.title,
    body: input.body,
    failure_reason: input.failureReason,
  };
  if (input.limit !== undefined) payload.limit = input.limit;
  return postJson('/context/trace-summary', payload);
}

export function truncatePrompt(text: string, maxChars?: number): Promise<TruncatePromptResult> {
  return postJson('/prompts/truncate', maxChars === undefined ? { text } : { text, max_chars: maxChars });
}
