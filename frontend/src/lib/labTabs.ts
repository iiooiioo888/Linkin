/**
 * 實驗室子分頁。分組與系統四類對齊：核心的開發組件、minecraft組件、價格分析探針組件、整合。
 */
export type LabSubTab = 'prompt' | 'firecrawl' | 'archify' | 'ponytail' | 'quant' | 'maps' | 'mcp' | 'ab' | 'runner';

export type LabTabItem = {
  key: LabSubTab;
  icon: string;
  label: string;
  hint?: string;
  /** 上游專案 */
  upstream?: { name: string; url: string };
};

/** 離開實驗室、打開既有畫面的項目。 */
export type LabLinkItem = {
  key: string;
  icon: string;
  label: string;
  hint?: string;
  href: string;
};

export type LabNavEntry = LabTabItem | LabLinkItem;

export function isLabLink(item: LabNavEntry): item is LabLinkItem {
  return 'href' in item;
}

const PROMPT: LabTabItem = {
  key: 'prompt',
  icon: '✎',
  label: '提示詞',
  hint: '優化與改寫',
  upstream: { name: 'prompt-optimizer', url: 'https://github.com/linshenkx/prompt-optimizer' },
};

const FIRECRAWL: LabTabItem = {
  key: 'firecrawl',
  icon: '◎',
  label: '爬蟲',
  hint: '網頁 → Markdown',
  upstream: { name: 'firecrawl', url: 'https://github.com/firecrawl/firecrawl' },
};

const ARCHIFY: LabTabItem = {
  key: 'archify',
  icon: '⬡',
  label: '架構',
  hint: '程式庫結構圖',
  upstream: { name: 'archify', url: 'https://github.com/tt-a1i/archify' },
};

const PONYTAIL: LabTabItem = {
  key: 'ponytail',
  icon: '✂',
  label: '精簡',
  hint: '審查與裁剪',
  upstream: { name: 'ponytail', url: 'https://github.com/DietrichGebert/ponytail' },
};

const QUANT: LabTabItem = {
  key: 'quant',
  icon: '◈',
  label: '策略庫',
  hint: '回測分類樹',
  upstream: { name: 'stock-quant', url: 'https://github.com/iiooiioo888/stock-quant' },
};

const MAPS: LabTabItem = {
  key: 'maps',
  icon: '▦',
  label: '策略圖',
  hint: '全部策略可視化',
  upstream: { name: 'archify', url: 'https://github.com/tt-a1i/archify' },
};

const RUNNER: LabTabItem = { key: 'runner', icon: '⎈', label: '容器', hint: '臨時 Docker 任務' };

const MCP: LabTabItem = { key: 'mcp', icon: '◇', label: 'MCP', hint: 'OPC／記憶／爬蟲開關' };

const AB: LabTabItem = { key: 'ab', icon: '▣', label: 'A/B', hint: '提示詞對照' };

const MINECRAFT_LINK: LabLinkItem = {
  key: 'minecraft',
  icon: '⛏',
  label: 'Minecraft',
  hint: '世界模組',
  href: '#/modules/minecraft',
};

const PRICE_PROBE_LINK: LabLinkItem = {
  key: 'price-probe',
  icon: '◉',
  label: '價格探針',
  hint: '廠商延遲與報價',
  href: '#/monitor/ops',
};

export const LAB_CORE_TABS: LabTabItem[] = [PROMPT, ARCHIFY, PONYTAIL, RUNNER, AB];

export const LAB_PRICE_TABS: LabTabItem[] = [QUANT, MAPS];

export const LAB_INTEGRATE_TABS: LabTabItem[] = [FIRECRAWL, MCP];

export const LAB_TABS: LabTabItem[] = [
  ...LAB_CORE_TABS,
  ...LAB_PRICE_TABS,
  ...LAB_INTEGRATE_TABS,
];

export type LabNavGroupId = 'core' | 'minecraft' | 'price' | 'integrate';

export type LabNavGroup = {
  id: LabNavGroupId;
  label: string;
  items: LabNavEntry[];
};

export const LAB_NAV_GROUPS: LabNavGroup[] = [
  { id: 'core', label: '核心的開發組件', items: LAB_CORE_TABS },
  { id: 'minecraft', label: 'minecraft組件', items: [MINECRAFT_LINK] },
  { id: 'price', label: '價格分析探針組件', items: [...LAB_PRICE_TABS, PRICE_PROBE_LINK] },
  { id: 'integrate', label: '整合', items: LAB_INTEGRATE_TABS },
];

export function labGroupForTab(tab: LabSubTab): LabNavGroup | undefined {
  return LAB_NAV_GROUPS.find((group) => group.items.some((item) => !isLabLink(item) && item.key === tab));
}

export function normalizeLabSubTab(tab: string | null | undefined): LabSubTab {
  if (tab && LAB_TABS.some((t) => t.key === tab)) return tab as LabSubTab;
  return 'prompt';
}

export function labSubTabLabel(tab: LabSubTab): string {
  return LAB_TABS.find((item) => item.key === tab)?.label ?? tab;
}
