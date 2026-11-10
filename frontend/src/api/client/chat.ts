/**
 * EvoLoop 後端 API 客戶端 — 聊天（Chat）：sendChat / sendChatStream / 路由預覽 / 回饋。
 *
 * 由原本的 api/client.ts 拆分而來；型別定義於 ../../types。
 */

import type { RoutingPreview, RoutingPreviewRequest } from '../../types';
import { attachGateHeaders } from '../../lib/auth';
import { parseRoutingPreview } from '../../lib/routingPreview';
import { apiUrl, parseBillingError } from './http';

export interface ChatOptions {
  /** 統一模式執行策略：auto（自動判斷）/ simple（單次生成）/ company（公司運行時） */
  executionStrategy?: 'auto' | 'simple' | 'company';
  /** 公司組織模板（execution_strategy 為 company 時生效） */
  companyTemplate?: string;
  /** 多輪對話歷史：[{"role": "user"|"assistant", "content": "..."}] */
  history?: Array<{ role: string; content: string }>;
  /** 需求審計官核發的戰術指令 */
  semantic_lock?: Record<string, unknown>;
}

export interface ChatBillingFootnote {
  credits_deducted?: number;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cache_write_tokens?: number;
  call_count?: number;
  models?: string[];
  pricing_version?: number;
  cache_savings_credits?: number;
  vendor_id?: string;
  session_id?: string;
  interrupted?: boolean;
  interrupt_reason?: string;
}

export interface ChatResult {
  session_id: string;
  answer: string;
  score: number | null;
  iteration: number;
  billing?: ChatBillingFootnote;
}

/** SSE 串流事件回調 */
export interface StreamCallbacks {
  onPhase?: (phase: string) => void;
  onPathResolved?: (preview: RoutingPreview) => void;
  onToken?: (token: string) => void;
  onAnswer?: (answer: string) => void;
  onEvaluation?: (score: number | null, iteration: number, multiDim?: import('../../types').MultiDimEvaluation) => void;
  onDone?: (answer: string, score: number | null, iteration: number, thinking?: string, billing?: ChatBillingFootnote) => void;
  onBilling?: (billing: ChatBillingFootnote) => void;
  onError?: (error: string) => void;
}

/**
 * 送出聊天並以 SSE 串流接收回答（打字機效果）。
 *
 * 統一模式：複雜任務（公司運行時路徑）會自動降級為同步回傳。
 * 回傳 AbortController 供取消請求。
 */
export function sendChatStream(
  query: string,
  sessionId: string,
  callbacks: StreamCallbacks,
  history?: Array<{ role: string; content: string }>,
  extra?: {
    semantic_lock?: Record<string, unknown>;
    ui_language?: string;
    executionStrategy?: 'auto' | 'simple' | 'company';
  },
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(
        apiUrl('/chat/stream'),
        attachGateHeaders({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query,
            session_id: sessionId,
            history: history ?? [],
            semantic_lock: extra?.semantic_lock ?? {},
            ui_language: extra?.ui_language ?? undefined,
            execution_strategy: extra?.executionStrategy ?? 'auto',
          }),
          signal: controller.signal,
        }),
      );

      if (!resp.ok) {
        callbacks.onError?.(await parseBillingError(resp));
        return;
      }
      if (!resp.body) {
        callbacks.onError?.('串流回應為空');
        return;
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // 解析 SSE 事件（以 \n\n 分隔）
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

          switch (eventType) {
            case 'path_resolved': {
              const preview = parseRoutingPreview(data);
              if (preview) callbacks.onPathResolved?.(preview);
              break;
            }
            case 'phase':
              if (String(data.phase ?? '') === 'path_resolved') break;
              callbacks.onPhase?.(String(data.phase ?? ''));
              break;
            case 'token':
              callbacks.onToken?.(String(data.token ?? ''));
              break;
            case 'answer':
              callbacks.onAnswer?.(String(data.answer ?? ''));
              break;
            case 'evaluation':
              callbacks.onEvaluation?.(
                (data.score as number) ?? null,
                (data.iteration as number) ?? 0,
                (data.multi_dim as import('../../types').MultiDimEvaluation) ?? undefined,
              );
              break;
            case 'billing':
              callbacks.onBilling?.(data as ChatBillingFootnote);
              break;
            case 'done':
              callbacks.onDone?.(
                String(data.answer ?? ''),
                (data.score as number) ?? null,
                (data.iteration as number) ?? 0,
                String(data.thinking ?? ''),
                (data.billing as ChatBillingFootnote) ?? undefined,
              );
              break;
            case 'error':
              callbacks.onError?.(String(data.error ?? '未知錯誤'));
              break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        callbacks.onError?.((err as Error).message || '網路連線失敗');
      }
    }
  })();

  return controller;
}

/** 發送前路由與成本預覽（純規則，與執行路徑同源）。 */
export async function fetchRoutingPreview(
  body: RoutingPreviewRequest,
  signal?: AbortSignal,
): Promise<RoutingPreview> {
  const resp = await fetch(
    apiUrl('/routing/preview'),
    attachGateHeaders({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    }),
  );
  if (!resp.ok) {
    throw new Error(`routing preview failed (${resp.status})`);
  }
  const data = (await resp.json()) as Record<string, unknown>;
  const preview = parseRoutingPreview(data);
  if (!preview) {
    throw new Error('routing preview invalid');
  }
  return preview;
}

/** 送出聊天並取得完整回答（統一模式）。 */
export async function sendChat(
  query: string,
  sessionId: string,
  options: ChatOptions = {},
): Promise<ChatResult> {
  let resp: Response;
  try {
    resp = await fetch(
      apiUrl('/chat'),
      attachGateHeaders({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query,
          session_id: sessionId,
          execution_strategy: options.executionStrategy ?? 'auto',
          company_template: options.companyTemplate ?? 'quick_task',
          history: options.history ?? [],
        }),
      }),
    );
  } catch {
    throw new Error('網路連線失敗，請檢查後端服務是否啟動');
  }

  if (!resp.ok) {
    throw new Error(await parseBillingError(resp));
  }
  const data = await resp.json();
  return {
    session_id: data.session_id ?? sessionId,
    answer: data.answer ?? '',
    score: data.score ?? null,
    iteration: data.iteration ?? 0,
    billing: data.billing as ChatBillingFootnote | undefined,
  };
}

/** 送出 👍/👎 回饋（盡力而為：後端尚未提供 /feedback 時靜默忽略）。 */
export async function sendFeedback(sessionId: string, rating: 1 | 2): Promise<void> {
  try {
    await fetch(apiUrl('/feedback'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, rating }),
    });
  } catch {
    // 後端未提供回饋端點時不影響體驗
  }
}
