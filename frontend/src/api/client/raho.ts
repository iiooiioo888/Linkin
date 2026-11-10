/**
 * EvoLoop 後端 API 客戶端 — RAHO 需求審計（Grill / L0 / 戰術指揮）。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { BattlePlanState, GrillUserState, L0Snapshot, RahoSnapshot } from '../../types';
import { apiUrl } from './http';

/** RAHO：需求審計官開場（聊天閘門，簡單寒暄可跳過）。 */
export async function startUserGrill(
  query: string,
  executionStrategy: 'auto' | 'simple' | 'company' = 'auto',
): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/raho/grill/start'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, execution_strategy: executionStrategy }),
  });
  if (!resp.ok) throw new Error(`需求審計啟動失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：回答審計追問。forceLock 視同過度授權，不會繞過五維門檻。 */
export async function turnUserGrill(
  sessionId: string,
  answer: string,
  forceLock = false,
): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/raho/grill/turn'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer, force_lock: forceLock }),
  });
  if (!resp.ok) throw new Error(`需求審計回合失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 強制前置閘門：一律開審。 */
export async function startAuditor(query: string): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/auditor/start'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) throw new Error(`需求審計官啟動失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 強制前置閘門：繼續追問。 */
export async function turnAuditor(
  sessionId: string,
  answer: string,
  forceLock = false,
): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/auditor/turn'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, answer, force_lock: forceLock }),
  });
  if (!resp.ok) throw new Error(`需求審計官回合失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** 強制前置閘門：SSE 回傳本輪拷問、五維評分與終態門票。 */
export async function streamAuditor(params: {
  query?: string;
  sessionId?: string;
  answer?: string;
  forceLock?: boolean;
}): Promise<GrillUserState> {
  const resp = await fetch(apiUrl('/auditor/stream'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: params.query ?? '',
      session_id: params.sessionId ?? '',
      answer: params.answer ?? '',
      force_lock: params.forceLock ?? false,
    }),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`需求審計官串流失敗（HTTP ${resp.status}）`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let result: GrillUserState | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const eventMatch = part.match(/^event:\s*(.+)$/m);
      const dataMatch = part.match(/^data:\s*(.+)$/m);
      if (!eventMatch || !dataMatch) continue;
      const eventType = eventMatch[1].trim();
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(dataMatch[1]);
      } catch {
        continue;
      }
      if (eventType === 'error') {
        throw new Error(String(data.error || '需求審計官串流失敗'));
      }
      if (eventType === 'done') {
        result = data as unknown as GrillUserState;
      }
    }
  }
  if (!result) throw new Error('需求審計官串流未回傳結果');
  return result;
}

/** RAHO：L0 環境與記憶核心。 */
export async function fetchL0Kernel(query = '', nodeId = ''): Promise<L0Snapshot> {
  const params = new URLSearchParams();
  if (query) params.set('query', query);
  if (nodeId) params.set('node_id', nodeId);
  const q = params.toString() ? `?${params.toString()}` : '';
  const resp = await fetch(apiUrl(`/raho/l0${q}`));
  if (!resp.ok) throw new Error(`讀取 L0 核心失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：質詢樹與決策阻塞點。 */
export async function fetchRahoTree(runId?: string): Promise<RahoSnapshot> {
  const q = runId ? `?run_id=${encodeURIComponent(runId)}` : '';
  const resp = await fetch(apiUrl(`/raho/tree${q}`));
  if (!resp.ok) throw new Error(`讀取質詢樹失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：L3 戰術指揮官拆解 L4 門票。 */
export async function planBattle(
  ticket?: Record<string, unknown> | null,
  lockedBrief = '',
): Promise<BattlePlanState> {
  const resp = await fetch(apiUrl('/raho/commander/plan'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ticket: ticket ?? undefined, locked_brief: lockedBrief, use_llm: false }),
  });
  if (!resp.ok) throw new Error(`戰術拆解失敗（HTTP ${resp.status}）`);
  return resp.json();
}

/** RAHO：用戶裁決熱馬桶圈。 */
export async function decideRaho(decisionId: string, choice: string, note = ''): Promise<RahoSnapshot> {
  const resp = await fetch(apiUrl('/raho/decide'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision_id: decisionId, choice, note }),
  });
  if (!resp.ok) {
    let detail = `裁決失敗（HTTP ${resp.status}）`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json();
}
