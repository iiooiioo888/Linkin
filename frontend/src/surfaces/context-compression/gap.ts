/** 上下文壓縮畫面的缺口說明。沒有可呼叫的壓縮 HTTP API，故只標缺口。 */

export const CONTEXT_COMPRESSION_ID = 'context-compression';

export const CONTEXT_COMPRESSION_LABEL = '上下文壓縮';

/** 內部壓縮函式存在，但沒有對應路由。 */
export const MISSING_COMPRESSION_APIS = [
  'backend.memory.context_compressor.compress',
  'backend.memory.context_compressor.extract_decisions',
  'backend.memory.context_compressor.summarize_trace',
  'backend.company.raho.context_bus.compress',
] as const;

/** 相近路由只讀寫記憶或回放軌跡，不執行壓縮。 */
export const NEARBY_ROUTES = [
  { route: 'GET /memories', does: '列出此帳號的記憶' },
  { route: 'DELETE /memories/{id}', does: '刪除單條記憶' },
  { route: 'POST /memories/cleanup', does: '清理過期或低品質記憶' },
  { route: 'GET /context', does: '回放最新軌跡的上下文洞察，含已發生的 context_compact 標記' },
  { route: 'GET /tasks/{task_id}/context', does: '回放指定任務的上下文洞察' },
] as const;

export const GAP_LEAD = '此畫面尚未接上壓縮。倉庫沒有可呼叫的上下文或記憶壓縮 API。';
