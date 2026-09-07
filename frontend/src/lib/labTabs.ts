/**
 * 實驗室子分頁 — Firecrawl / Prompt Optimizer / Archify / Ponytail / 策略庫 / 策略圖 等。
 */
export type LabSubTab = 'prompt' | 'firecrawl' | 'archify' | 'ponytail' | 'quant' | 'maps' | 'mcp' | 'ab';

export type LabTabItem = {
  key: LabSubTab;
  icon: string;
  label: string;
  hint?: string;
  /** 上游專案 */
  upstream?: { name: string; url: string };
};

/** 整合工具（上游專案）。 */
export const LAB_INTEGRATION_TABS: LabTabItem[] = [
  {
    key: 'prompt',
    icon: '✎',
    label: '提示詞',
    hint: '優化與改寫',
    upstream: { name: 'prompt-optimizer', url: 'https://github.com/linshenkx/prompt-optimizer' },
  },
  {
    key: 'firecrawl',
    icon: '◎',
    label: '爬蟲',
    hint: '網頁 → Markdown',
    upstream: { name: 'firecrawl', url: 'https://github.com/firecrawl/firecrawl' },
  },
  {
    key: 'archify',
    icon: '⬡',
    label: '架構',
    hint: '程式庫結構圖',
    upstream: { name: 'archify', url: 'https://github.com/tt-a1i/archify' },
  },
  {
    key: 'ponytail',
    icon: '✂',
    label: '精簡',
    hint: '審查與裁剪',
    upstream: { name: 'ponytail', url: 'https://github.com/DietrichGebert/ponytail' },
  },
  {
    key: 'quant',
    icon: '◈',
    label: '策略庫',
    hint: '回測分類樹',
    upstream: { name: 'stock-quant', url: 'https://github.com/iiooiioo888/stock-quant' },
  },
  {
    key: 'maps',
    icon: '▦',
    label: '策略圖',
    hint: '全部策略可視化',
    upstream: { name: 'archify', url: 'https://github.com/tt-a1i/archify' },
  },
];

export const LAB_EXTRA_TABS: LabTabItem[] = [
  { key: 'mcp', icon: '◇', label: 'MCP', hint: 'OPC／記憶／爬蟲開關' },
  { key: 'ab', icon: '▣', label: 'A/B', hint: '提示詞對照' },
];

export const LAB_TABS: LabTabItem[] = [...LAB_INTEGRATION_TABS, ...LAB_EXTRA_TABS];

export type LabNavGroup = {
  id: 'integrate' | 'experiment';
  label: string;
  items: LabTabItem[];
};

export const LAB_NAV_GROUPS: LabNavGroup[] = [
  { id: 'integrate', label: '整合', items: LAB_INTEGRATION_TABS },
  { id: 'experiment', label: '實驗', items: LAB_EXTRA_TABS },
];

export function normalizeLabSubTab(tab: string | null | undefined): LabSubTab {
  if (tab && LAB_TABS.some((t) => t.key === tab)) return tab as LabSubTab;
  return 'prompt';
}

export function labSubTabLabel(tab: LabSubTab): string {
  return LAB_TABS.find((item) => item.key === tab)?.label ?? tab;
}
