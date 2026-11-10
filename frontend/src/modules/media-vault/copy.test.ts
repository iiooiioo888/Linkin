import { describe, expect, it } from 'vitest';

/** UX-011：媒體庫 Hub 可見文案須為繁體。 */
describe('Media Vault zh-Hant copy', () => {
  const forbidden = ['采集', '媒体库', '媒体', '监控', '图库', '尚无媒资', '相关仓库'];

  it('MediaVaultHub source has no Simplified UI literals', async () => {
    const src = await import.meta.glob('./*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<
      string,
      string
    >;
    const hub = src['./MediaVaultHub.tsx'] ?? '';
    for (const word of forbidden) {
      expect(hub.includes(word), `found ${word} in MediaVaultHub`).toBe(false);
    }
    expect(hub.includes('採集 · 媒體庫')).toBe(true);
    expect(hub.includes('監控')).toBe(true);
    expect(hub.includes('圖庫')).toBe(true);
  });
});
