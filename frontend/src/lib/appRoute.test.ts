import { describe, expect, it } from 'vitest';
import { buildAppRouteHash, getDefaultRoute, parseAppRoute } from './appRoute';

describe('company page route', () => {
  it('keeps #/company as its own full-page view', () => {
    const route = parseAppRoute('#/company');
    expect(route.view).toBe('company');
    expect(buildAppRouteHash(route)).toBe('#/company');
    expect(parseAppRoute(buildAppRouteHash({ ...getDefaultRoute(), view: 'company' })).view).toBe('company');
  });

  it('does not steal chat or raho hashes', () => {
    expect(parseAppRoute('#/chat').view).toBe('chat');
    expect(parseAppRoute('#/raho/run-1').view).toBe('raho');
    expect(parseAppRoute('#/raho/run-1').rahoFocus).toBe('run-1');
  });
});
