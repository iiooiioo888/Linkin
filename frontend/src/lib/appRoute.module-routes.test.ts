import { beforeAll, describe, expect, it } from 'vitest';
import { registerLocalVideoStudioModule } from '../modules/local-video-studio/register';
import { registerMediaVaultModule } from '../modules/media-vault/register';
import { applyRemoteModules, type WorldModuleSpec } from './worldModules';
import { buildAppRouteHash, parseAppRoute, routesEqual } from './appRoute';

const MEDIA_VAULT_SPEC: WorldModuleSpec = {
  id: 'media-vault',
  title: 'Media Vault',
  description: '',
  version: '1.0.0',
  kind: 'integration',
  icon: 'generic',
  defaultPage: 'control',
  enabled: true,
  apiPrefix: '/media-vault',
  gatewayPrefix: '/modules/media-vault/api',
  capabilities: [],
  navGroups: [
    {
      id: 'panels',
      label: '採集媒資',
      items: [
        { key: 'control', icon: '⎈', label: '控制' },
        { key: 'gallery', icon: '▦', label: '圖庫' },
        { key: 'monitor', icon: '◉', label: '監控' },
      ],
    },
  ],
};

const LVS_SPEC: WorldModuleSpec = {
  id: 'local-video-studio',
  title: 'Local Video Studio',
  description: '',
  version: '0.2.0',
  kind: 'integration',
  icon: 'generic',
  defaultPage: 'projects',
  enabled: true,
  apiPrefix: '/local-video-studio',
  gatewayPrefix: '/modules/local-video-studio/api',
  capabilities: [],
  navGroups: [
    {
      id: 'studio',
      label: '影片工作室',
      items: [
        { key: 'projects', icon: '▶', label: '專案' },
        { key: 'shots', icon: '▦', label: '鏡頭板' },
        { key: 'jobs', icon: '◎', label: '任務' },
      ],
    },
  ],
};

beforeAll(() => {
  applyRemoteModules([MEDIA_VAULT_SPEC, LVS_SPEC]);
  registerMediaVaultModule();
  registerLocalVideoStudioModule();
});

describe('module-scoped hash routes (UX-009 / UX-010)', () => {
  it('keeps Media Vault monitor in media-vault namespace', () => {
    const route = parseAppRoute('#/modules/media-vault/monitor');
    expect(route.worldModuleId).toBe('media-vault');
    expect(route.monitorTab).toBe('monitor');
    expect(route.view).toBe('monitor');
    const hash = buildAppRouteHash(route);
    expect(hash).toBe('#/world/media-vault/monitor');
    expect(hash).not.toContain('minecraft');
  });

  it('round-trips Media Vault monitor without rewriting to Minecraft', () => {
    const parsed = parseAppRoute('#/modules/media-vault/monitor');
    const rebuilt = parseAppRoute(buildAppRouteHash(parsed));
    expect(rebuilt.worldModuleId).toBe('media-vault');
    expect(rebuilt.monitorTab).toBe('monitor');
    expect(routesEqual(parsed, rebuilt)).toBe(true);
  });

  it('resolves LVS review / compose / resources inside Hub', () => {
    for (const page of ['review', 'compose', 'resources'] as const) {
      const route = parseAppRoute(`#/modules/local-video-studio/${page}`);
      expect(route.worldModuleId).toBe('local-video-studio');
      expect(route.monitorTab).toBe(page);
      expect(route.view).toBe('monitor');
      expect(buildAppRouteHash(route)).toBe(`#/world/local-video-studio/${page}`);
    }
  });

  it('does not regress LVS jobs / shots / detail', () => {
    expect(parseAppRoute('#/modules/local-video-studio/jobs').monitorTab).toBe('jobs');
    expect(parseAppRoute('#/modules/local-video-studio/shots').monitorTab).toBe('shots');
    expect(parseAppRoute('#/modules/local-video-studio/detail').monitorTab).toBe('detail');
    expect(parseAppRoute('#/modules/local-video-studio/jobs').worldModuleId).toBe('local-video-studio');
  });

  it('does not send LVS review to observe overview', () => {
    const route = parseAppRoute('#/modules/local-video-studio/review');
    expect(buildAppRouteHash(route)).not.toBe('#/observe/overview');
  });
});
