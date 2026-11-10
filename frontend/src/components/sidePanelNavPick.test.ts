import { describe, expect, it } from 'vitest';
import { sidePanelMonitorPick } from './sidePanelNavPick';

describe('SidePanel nav pick (duplicate page keys)', () => {
  const navItems = [
    { key: 'monitor' as const, worldModuleId: 'minecraft' },
    { key: 'monitor' as const, worldModuleId: 'media-vault' },
  ];

  it('first-key-wins lookup would hijack Media Vault monitor to Minecraft', () => {
    const first = navItems.find((item) => item.key === 'monitor');
    expect(first?.worldModuleId).toBe('minecraft');
  });

  it('uses clicked item worldModuleId for Media Vault monitor', () => {
    const clicked = navItems[1];
    const pick = sidePanelMonitorPick(clicked.key, clicked.worldModuleId);
    expect(pick).toEqual({ tab: 'monitor', worldModuleId: 'media-vault' });
    expect(pick.worldModuleId).not.toBe('minecraft');
  });

  it('uses clicked item worldModuleId for Minecraft monitor', () => {
    const clicked = navItems[0];
    expect(sidePanelMonitorPick(clicked.key, clicked.worldModuleId)).toEqual({
      tab: 'monitor',
      worldModuleId: 'minecraft',
    });
  });
});
