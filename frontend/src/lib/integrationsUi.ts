/**
 * 外部整合 GUI 元資料（MemOS／OpenViking／WeKnora／Yao／Ouroboros／OpenPencil）。
 * 與 backend/integrations/api.py INTEGRATION_CATALOG 對齊；UI 不得自行推導審計分數。
 */
import type { IntegrationGroup, IntegrationStatus } from '../api/integrations';

export const INTEGRATION_ORDER = [
  'memos',
  'openviking',
  'weknora',
  'yao',
  'ouroboros',
  'openpencil',
] as const;

export type IntegrationName = (typeof INTEGRATION_ORDER)[number];

export type IntegrationUiMeta = {
  name: IntegrationName;
  short: string;
  label: string;
  group: IntegrationGroup;
  glyph: string;
  hint: string;
  accent: string;
};

export const INTEGRATION_META: Record<IntegrationName, IntegrationUiMeta> = {
  memos: {
    name: 'memos',
    short: 'MemOS',
    label: 'MemOS',
    group: 'recall',
    glyph: '◌',
    hint: '長期記憶召回 · token 節省',
    accent: '#64D2FF',
  },
  openviking: {
    name: 'openviking',
    short: 'Viking',
    label: 'OpenViking',
    group: 'recall',
    glyph: '⬡',
    hint: 'L0／L1 分層上下文',
    accent: '#5E6AD2',
  },
  weknora: {
    name: 'weknora',
    short: 'WeKnora',
    label: 'WeKnora',
    group: 'recall',
    glyph: '◈',
    hint: '企業 RAG 知識庫',
    accent: '#30D158',
  },
  yao: {
    name: 'yao',
    short: 'Yao',
    label: 'Yao',
    group: 'agent',
    glyph: '▣',
    hint: 'Agent 工作區／任務板',
    accent: '#FF9F0A',
  },
  ouroboros: {
    name: 'ouroboros',
    short: 'Ouro',
    label: 'Ouroboros',
    group: 'agent',
    glyph: '⟳',
    hint: '訪談閘門／三階段評估',
    accent: '#BF5AF2',
  },
  openpencil: {
    name: 'openpencil',
    short: 'Pencil',
    label: 'OpenPencil',
    group: 'design',
    glyph: '✎',
    hint: 'Design-as-Code 顯式生成',
    accent: '#FF375F',
  },
};

export const GROUP_LABEL: Record<IntegrationGroup, { label: string; hint: string }> = {
  recall: { label: 'Token 節省召回', hint: 'MemOS · OpenViking · WeKnora' },
  agent: { label: 'Agent 工作流', hint: 'Yao · Ouroboros' },
  design: { label: '設計生成', hint: 'OpenPencil' },
};

export function isIntegrationName(raw: string | null | undefined): raw is IntegrationName {
  return Boolean(raw && (INTEGRATION_ORDER as readonly string[]).includes(raw));
}

export function metaOf(name: string): IntegrationUiMeta | null {
  return isIntegrationName(name) ? INTEGRATION_META[name] : null;
}

/** 深鏈：#/monitor/integrations 或 #/monitor/integrations/{name} */
export function jumpToIntegration(name?: IntegrationName | string | null) {
  if (name && isIntegrationName(name)) {
    window.location.hash = `#/monitor/integrations/${name}`;
    return;
  }
  window.location.hash = '#/monitor/integrations';
}

export function parseIntegrationFocus(hash = window.location.hash): IntegrationName | null {
  const raw = hash.replace(/^#/, '').replace(/^\/?/, '');
  const parts = raw.split('/').filter(Boolean);
  if (parts[0] === 'monitor' && parts[1] === 'integrations' && isIntegrationName(parts[2])) {
    return parts[2];
  }
  // 別名：#/monitor/memos 等（monitorTabs 會落到 integrations）
  if (parts[0] === 'monitor' && isIntegrationName(parts[1])) {
    return parts[1];
  }
  return null;
}

export type IntegrationTone = 'off' | 'ok' | 'warn' | 'err';

export function toneOf(item: IntegrationStatus | undefined): IntegrationTone {
  if (!item || !item.enabled) return 'off';
  if (item.health?.ok === false) return 'err';
  if (item.health?.reason_code && item.health.reason_code !== 'integration:disabled') {
    // enabled 但未探測到 ok=true 時視為 warn
    if (item.health.ok !== true) return 'warn';
  }
  return item.health?.ok === true ? 'ok' : 'warn';
}

export function summarizeIntegrations(items: IntegrationStatus[]): {
  enabled: number;
  healthy: number;
  degraded: number;
  total: number;
} {
  const total = items.length || INTEGRATION_ORDER.length;
  let enabled = 0;
  let healthy = 0;
  let degraded = 0;
  for (const item of items) {
    if (!item.enabled) continue;
    enabled += 1;
    if (item.health?.ok === false) degraded += 1;
    else if (item.health?.ok === true) healthy += 1;
  }
  return { enabled, healthy, degraded, total };
}
