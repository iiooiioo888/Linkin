/**
 * 實驗室面板共用常數與樣式輔助。
 */

export const DEMO_BEFORE = `你是一位工業助手。根據感測資料回答問題。
請盡量詳細說明。`;

export const MCP_TOOLS = [
  { id: 'opc.read', name: 'OPC Read', desc: '讀取白名單標籤', enabled: true, risk: 'low', fn: '工業接線' },
  { id: 'opc.write', name: 'OPC Write', desc: '經護欄寫入', enabled: true, risk: 'high', fn: '工業接線' },
  { id: 'memory.search', name: 'Memory Search', desc: '向量記憶檢索', enabled: true, risk: 'low', fn: '召回' },
  { id: 'firecrawl.scrape', name: 'Firecrawl Scrape', desc: '網頁 → Markdown', enabled: true, risk: 'mid', fn: '採集' },
  { id: 'docker.inspect', name: 'Docker Inspect', desc: '容器狀態查詢', enabled: false, risk: 'mid', fn: '容器' },
];

export const MCP_FUNCTIONS = ['工業接線', '召回', '採集', '容器'] as const;

export const AB_SERIES = [
  { name: '準確', a: 7.2, b: 8.6 },
  { name: '完整', a: 6.8, b: 8.1 },
  { name: '清晰', a: 7.5, b: 8.4 },
  { name: '相關', a: 7.0, b: 8.9 },
  { name: '延遲↓', a: 4.2, b: 6.8 },
];

export function tabBtn(active: boolean) {
  return `shrink-0 rounded-full px-3 py-1.5 text-[12px] font-bold transition-colors ${
    active ? 'bg-[var(--console-accent)] text-white' : 'bg-white/[0.04] text-[var(--console-sub)] hover:text-[var(--console-ink)]'
  }`;
}

export type McpTool = (typeof MCP_TOOLS)[number];
