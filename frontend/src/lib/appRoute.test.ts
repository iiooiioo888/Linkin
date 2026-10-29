import { describe, expect, it } from 'vitest';
import { buildAppRouteHash, getDefaultRoute, parseAppRoute, takeSkillFocus } from './appRoute';

describe('Phase1 routes + aliases', () => {
  it('maps #/work/company and keeps old #/company readable', () => {
    expect(parseAppRoute('#/company').view).toBe('company');
    expect(parseAppRoute('#/work/company').view).toBe('company');
    expect(buildAppRouteHash({ ...getDefaultRoute(), view: 'company' })).toBe('#/work/company');
  });

  it('remembers a skill deep link on new and old paths', () => {
    const route = parseAppRoute('#/settings/skills/agent-reach');
    expect(route.monitorTab).toBe('skills');
    expect(takeSkillFocus()).toBe('agent-reach');
    expect(takeSkillFocus()).toBeNull();
    const legacy = parseAppRoute('#/monitor/skills/agent-reach');
    expect(legacy.monitorTab).toBe('skills');
    expect(takeSkillFocus()).toBe('agent-reach');
  });

  it('dual-reads chat and raho hashes', () => {
    expect(parseAppRoute('#/chat').view).toBe('chat');
    expect(parseAppRoute('#/work/chat').view).toBe('chat');
    expect(buildAppRouteHash({ ...getDefaultRoute(), view: 'chat' })).toBe('#/work/chat');
    expect(parseAppRoute('#/raho/run-1').view).toBe('raho');
    expect(parseAppRoute('#/raho/run-1').rahoFocus).toBe('run-1');
    expect(parseAppRoute('#/work/company/raho/run-1').rahoFocus).toBe('run-1');
  });

  it('opens the role desk for the old pipeline hash and writes new path', () => {
    const route = parseAppRoute('#/monitor/pipeline');
    expect(route.view).toBe('monitor');
    expect(route.monitorTab).toBe('agents');
    expect(buildAppRouteHash(route)).toBe('#/observe/agents');
  });

  it('maps plane paths for compute / supply / assets / observe', () => {
    expect(parseAppRoute('#/compute/models').monitorTab).toBe('models');
    expect(parseAppRoute('#/compute/exec').monitorTab).toBe('exec');
    expect(parseAppRoute('#/supply/quota').monitorTab).toBe('quota');
    expect(parseAppRoute('#/supply/health').monitorTab).toBe('health');
    expect(parseAppRoute('#/assets/memory').monitorTab).toBe('memory');
    expect(parseAppRoute('#/observe/overview').monitorTab).toBe('live');
    expect(parseAppRoute('#/settings/routes').monitorTab).toBe('llm');
    expect(buildAppRouteHash({ ...getDefaultRoute(), view: 'monitor', monitorTab: 'models' })).toBe(
      '#/compute/models',
    );
  });

  it('dual-reads world vs modules', () => {
    const a = parseAppRoute('#/modules/minecraft');
    const b = parseAppRoute('#/world/minecraft');
    expect(a.monitorTab).toBe(b.monitorTab);
    expect(buildAppRouteHash(a).startsWith('#/world/')).toBe(true);
  });
});
