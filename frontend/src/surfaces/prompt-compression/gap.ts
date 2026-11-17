/** 提示詞壓縮畫面的缺口。倉庫沒有可呼叫的壓縮 API。 */

export const PROMPT_COMPRESSION_GAP = {
  status: '缺口',
  missing: '提示詞壓縮 HTTP API',
  detail: '倉庫沒有接受提示詞並回傳較短結果的端點，這個畫面不能送出文字。',
  notThis: {
    method: 'POST',
    path: '/lab/prompt/optimize',
    why: '這是提示詞優化，會經後端 LLM 改寫，不是壓縮。',
  },
  internalOnly: [
    'backend.memory.context_compressor.compress',
    'backend.company.raho.context_bus.compress',
    'backend.prompts.templates.truncate',
  ],
} as const;
