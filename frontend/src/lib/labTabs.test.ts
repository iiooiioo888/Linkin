import { describe, expect, it } from 'vitest';
import { LAB_NAV_GROUPS, LAB_TABS, isLabLink, labGroupForTab } from './labTabs';

describe('lab component groups', () => {
  it('uses the four product classes', () => {
    expect(LAB_NAV_GROUPS.map((group) => group.label)).toEqual([
      '核心的開發組件',
      'minecraft組件',
      '價格分析探針組件',
      '整合',
    ]);
  });

  it('places each lab tool in one class', () => {
    expect(labGroupForTab('prompt')?.id).toBe('core');
    expect(labGroupForTab('archify')?.id).toBe('core');
    expect(labGroupForTab('ponytail')?.id).toBe('core');
    expect(labGroupForTab('runner')?.id).toBe('core');
    expect(labGroupForTab('ab')?.id).toBe('core');
    expect(labGroupForTab('quant')?.id).toBe('price');
    expect(labGroupForTab('maps')?.id).toBe('price');
    expect(labGroupForTab('firecrawl')?.id).toBe('integrate');
    expect(labGroupForTab('mcp')?.id).toBe('integrate');
    expect(LAB_TABS).toHaveLength(9);
  });

  it('splits 整合 by function', () => {
    const group = LAB_NAV_GROUPS.find((item) => item.id === 'integrate');
    expect(group?.sections?.map((section) => section.label)).toEqual([
      '召回',
      '採集',
      '工業接線',
      'Agent 工作流',
      '設計',
      '技能',
    ]);
    expect(group?.sections?.find((section) => section.id === 'crawl')?.items.map((item) => item.label)).toEqual([
      '爬蟲',
      '社媒',
      'Agent Reach',
    ]);
    const reach = group?.sections
      ?.find((section) => section.id === 'crawl')
      ?.items.find((item) => item.key === 'agent-reach');
    expect(reach && isLabLink(reach) ? reach.href : '').toBe('#/monitor/skills/agent-reach');
    expect(group?.sections?.find((section) => section.id === 'wire')?.items.map((item) => item.key)).toEqual(['mcp']);
  });

  it('links minecraft and the price probe out of the lab', () => {
    const minecraft = LAB_NAV_GROUPS.find((group) => group.id === 'minecraft')?.items[0];
    const probe = LAB_NAV_GROUPS.find((group) => group.id === 'price')?.items.find((item) => isLabLink(item));
    expect(minecraft && isLabLink(minecraft) ? minecraft.href : '').toBe('#/modules/minecraft');
    expect(probe && isLabLink(probe) ? probe.href : '').toBe('#/monitor/ops');
  });
});
