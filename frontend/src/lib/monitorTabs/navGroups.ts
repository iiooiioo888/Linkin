/**
 * 側欄分組資料（Phase1 各活動＋舊控制台樹）與分組查詢 helpers。
 */
import type { MonitorTab } from '../../components/AppShell';
import { getWorldModule, isModuleActivity, listWorldModules } from '../worldModules';
import type { ModuleNavGroup, ModuleNavItem } from '../worldModules';
import { normalizeDeskActivity } from './activity';
import { monitorTabLabel } from './tabs';
import type { ActivityKey, ConsoleNavItem, ConsoleNavKey, MonitorNavGroup, MonitorTabItem } from './types';

export const TRACES_NAV_ITEM: ConsoleNavItem = {
  key: 'traces',
  icon: '☰',
  label: '軌跡',
  hint: '執行步驟',
};

/** Phase1 側欄：工作 */
export const WORK_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'work',
    label: '工作',
    items: [
      { key: 'chat', icon: '◎', label: '對話', hint: 'Linkin 決定做什麼' },
      { key: 'tasks', icon: '▣', label: '任務', hint: '隊列／執行中／已完成' },
      TRACES_NAV_ITEM,
      { key: 'company', icon: '⌂', label: '席位／公司', hint: '席位與交辦' },
      { key: 'approvals', icon: '✓', label: '審批佇列', hint: 'A2 前未開通' },
    ],
  },
];

/** Phase1 側欄：觀測 */
export const OBSERVE_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'observe',
    label: '觀測',
    items: [
      { key: 'live', icon: '◎', label: 'Agent 總覽', hint: '首屏指標' },
      { key: 'agents', icon: '◈', label: '角色工作台', hint: '角色工作台' },
      { key: 'feedback', icon: '♥', label: '用戶反饋', hint: '評分與審計留痕' },
    ],
  },
];

/** Phase1 側欄：計算（AI-Core） */
export const COMPUTE_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'compute',
    label: '計算',
    plane: 'ai-core',
    items: [
      { key: 'models', icon: '◉', label: '模型與成本', hint: 'Token 延遲與模型成本 · AI-Core' },
      { key: 'exec', icon: '⬡', label: '執行環境', hint: '沙箱／Exec · 無資料則空態' },
    ],
  },
];

/** Phase1 側欄：供給（Cloud Core） */
export const SUPPLY_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'supply',
    label: '供給',
    plane: 'cloud-core',
    items: [
      { key: 'quota', icon: '▤', label: '容量與配額', hint: 'Cloud Core 配額帳本' },
      { key: 'health', icon: '◇', label: '節點健康', hint: '節點／基礎設施健康' },
    ],
  },
];

/** Phase1 側欄：資產 */
export const ASSETS_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'assets',
    label: '資產',
    plane: 'assets',
    items: [
      { key: 'context', icon: '◫', label: 'Context', hint: '資產層只存與取' },
      { key: 'memory', icon: '◌', label: '記憶瀏覽', hint: '只存與取，不決策' },
    ],
  },
];

/** Phase1 側欄：設定 */
export const SETTINGS_NAV_GROUPS: MonitorNavGroup[] = [
  {
    id: 'settings',
    label: '設定',
    items: [
      { key: 'llm', icon: '⊞', label: 'API 路由', hint: '金鑰、目錄、分發' },
      { key: 'skills', icon: '⚡', label: '技能與 MCP', hint: '技能庫／MCP' },
      { key: 'integrations', icon: '⧉', label: '外部整合', hint: '召回／工作流／設計' },
      { key: 'ops', icon: '⚙', label: '基礎設施', hint: 'Hub／檢查點／連線池' },
      { key: 'lab', icon: '✦', label: '實驗室', hint: '開發工具' },
      { key: 'metrics', icon: '◇', label: '系統總覽', hint: '快取／反思／優化' },
    ],
  },
];

/** 舊單一控制台樹（相容匯出；新碼用分活動組） */
export const CONSOLE_NAV_GROUPS: MonitorNavGroup[] = [
  ...OBSERVE_NAV_GROUPS,
  {
    id: 'execute',
    label: '執行',
    items: [
      { key: 'tasks', icon: '▣', label: '任務', hint: '隊列／執行中／已完成' },
      TRACES_NAV_ITEM,
    ],
  },
  {
    id: 'roles',
    label: '角色',
    items: [{ key: 'agents', icon: '◈', label: '角色', hint: '角色工作台' }],
  },
  ...COMPUTE_NAV_GROUPS,
  ...ASSETS_NAV_GROUPS,
  ...SETTINGS_NAV_GROUPS,
];

function moduleNavAsGroups(id: string): MonitorNavGroup[] {
  const spec = getWorldModule(id);
  if (!spec) return [];
  return spec.navGroups.map((group: ModuleNavGroup) => ({
    id: group.id,
    label: group.label,
    items: group.items.map((item: ModuleNavItem) => ({
      key: item.key as ConsoleNavKey,
      icon: item.icon,
      label: item.label,
      hint: item.hint,
      worldModuleId: id,
    })),
  }));
}

function allNavGroups(): MonitorNavGroup[] {
  return [
    ...WORK_NAV_GROUPS,
    ...OBSERVE_NAV_GROUPS,
    ...COMPUTE_NAV_GROUPS,
    ...SUPPLY_NAV_GROUPS,
    ...ASSETS_NAV_GROUPS,
    ...SETTINGS_NAV_GROUPS,
    ...listWorldModules().flatMap((spec) => moduleNavAsGroups(spec.id)),
  ];
}

export const MONITOR_NAV_GROUPS: MonitorNavGroup[] = CONSOLE_NAV_GROUPS;

export function navGroupsForActivity(activity: ActivityKey): MonitorNavGroup[] {
  const resolved = normalizeDeskActivity(activity);
  if (resolved === 'work') return WORK_NAV_GROUPS;
  if (resolved === 'observe') return OBSERVE_NAV_GROUPS;
  if (resolved === 'compute') return COMPUTE_NAV_GROUPS;
  if (resolved === 'supply') return SUPPLY_NAV_GROUPS;
  if (resolved === 'assets') return ASSETS_NAV_GROUPS;
  if (resolved === 'settings') return SETTINGS_NAV_GROUPS;
  if (resolved === 'world') {
    const modules = listWorldModules();
    if (modules.length === 0) return [];
    return modules.flatMap((spec) => moduleNavAsGroups(spec.id));
  }
  if (isModuleActivity(String(activity))) return moduleNavAsGroups(String(activity));
  return [];
}

export function navItemsForActivity(activity: ActivityKey): MonitorTabItem[] {
  return navGroupsForActivity(activity).flatMap((group) =>
    group.items
      .filter((item) => item.key !== 'traces' && item.key !== 'chat' && item.key !== 'company')
      .map((item) => ({ key: item.key as MonitorTab, icon: item.icon, label: item.label })),
  );
}

export function navGroupForTab(tab: ConsoleNavKey): MonitorNavGroup['id'] | null {
  return allNavGroups().find((g) => g.items.some((i) => i.key === tab))?.id ?? null;
}

export function navPathForTab(tab: ConsoleNavKey): string {
  const group = allNavGroups().find((g) => g.items.some((i) => i.key === tab));
  const item = group?.items.find((i) => i.key === tab);
  if (!group || !item) return item?.label ?? monitorTabLabel(tab as MonitorTab);
  return `${group.label} → ${item.label}`;
}
