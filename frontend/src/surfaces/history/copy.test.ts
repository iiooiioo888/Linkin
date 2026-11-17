import { describe, expect, it } from 'vitest';

const forbidden = ['历史', '对话', '记录', '继续', '打开', '会话', '还没有', '没有内容', '分钟', '小时', '刚刚', '响应', '选择'];

describe('history surface copy', () => {
  it('mounts id, label, and Page in Traditional Chinese', async () => {
    const mountFiles = import.meta.glob('../../routes/mounts/history.ts', {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const mount = Object.values(mountFiles).join('\n');
    expect(mount).toContain("export const id = 'history'");
    expect(mount).toContain("export const label = '歷史對話記錄'");
    expect(mount).toContain('export const Page = HistoryPage');

    const surfaceFiles = import.meta.glob(['./Page.tsx', './model.ts'], {
      query: '?raw',
      import: 'default',
      eager: true,
    }) as Record<string, string>;
    const surface = Object.values(surfaceFiles).join('\n');
    const source = `${mount}\n${surface}`;
    for (const word of forbidden) {
      expect(source.includes(word), `found ${word}`).toBe(false);
    }
    expect(surface).toContain('歷史對話記錄');
    expect(surface).toContain('選擇一筆，在對話裡繼續。');
    expect(surface).toContain('還沒有對話。');
    expect(surface).toContain('前往對話');
    expect(surface).toContain('繼續');
    expect(surface).toContain('本機儲存');
    expect(surface).toContain('找不到這段對話');
  });
});
