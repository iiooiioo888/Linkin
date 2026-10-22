import { describe, expect, it } from 'vitest';
import { buildAppRouteHash, getDefaultRoute, parseAppRoute, takeSkillFocus } from './appRoute';

describe('company page route', () => {
  it('keeps #/company as its own full-page view', () => {
    const route = parseAppRoute('#/company');
    expect(route.view).toBe('company');
    expect(buildAppRouteHash(route)).toBe('#/company');
    expect(parseAppRoute(buildAppRouteHash({ ...getDefaultRoute(), view: 'company' })).view).toBe('company');
  });

  it('remembers a skill deep link for the skills page', () => {
    const route = parseAppRoute('#/monitor/skills/agent-reach');
    expect(route.monitorTab).toBe('skills');
    expect(takeSkillFocus()).toBe('agent-reach');
    expect(takeSkillFocus()).toBeNull();
  });

  it('does not steal chat or raho hashes', () => {
    expect(parseAppRoute('#/chat').view).toBe('chat');
    expect(parseAppRoute('#/raho/run-1').view).toBe('raho');
    expect(parseAppRoute('#/raho/run-1').rahoFocus).toBe('run-1');
  });

  it('opens the role desk for the old pipeline hash', () => {
    const route = parseAppRoute('#/monitor/pipeline');
    expect(route.view).toBe('monitor');
    expect(route.monitorTab).toBe('agents');
    expect(buildAppRouteHash(route)).toBe('#/monitor/agents');
  });
});
