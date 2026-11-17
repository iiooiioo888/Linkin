import { describe, expect, it } from 'vitest';
import {
  SURFACE_LABEL,
  SURFACE_ORDER,
  listSurfaces,
  surfaceFromHash,
} from './catalog';

const REMOVED = ['公司', '席位', 'OPC', '實驗室', '媒體庫', '影片工作室', '觀測', '模組'];

describe('使用者看得見的入口', () => {
  it('只保留四個固定入口', () => {
    expect([...SURFACE_ORDER]).toEqual([
      'chat',
      'context-compression',
      'prompt-compression',
      'history',
    ]);
    expect(SURFACE_ORDER.map((id) => SURFACE_LABEL[id])).toEqual([
      '對話',
      '上下文壓縮',
      '提示詞壓縮',
      '歷史對話記錄',
    ]);
    const entries = listSurfaces({});
    expect(entries.map((entry) => entry.id)).toEqual([...SURFACE_ORDER]);
    expect(entries.map((entry) => entry.label)).toEqual([
      '對話',
      '上下文壓縮',
      '提示詞壓縮',
      '歷史對話記錄',
    ]);
    expect(entries.every((entry) => entry.ready === false)).toBe(true);
  });

  it('已掛載的頁面接上，其餘顯示為未接上', () => {
    const Page = () => null;
    const entries = listSurfaces({
      './mounts/chat.ts': { id: 'chat', label: '對話', Page },
    });
    expect(entries.find((entry) => entry.id === 'chat')).toMatchObject({
      ready: true,
      label: '對話',
    });
    expect(entries.filter((entry) => !entry.ready).map((entry) => entry.id)).toEqual([
      'context-compression',
      'prompt-compression',
      'history',
    ]);
  });

  it('舊的公司、模組、實驗室網址回到對話', () => {
    expect(surfaceFromHash('#/chat')).toBe('chat');
    expect(surfaceFromHash('#/context-compression')).toBe('context-compression');
    expect(surfaceFromHash('#/prompt-compression')).toBe('prompt-compression');
    expect(surfaceFromHash('#/history')).toBe('history');
    expect(surfaceFromHash('#/company')).toBe('chat');
    expect(surfaceFromHash('#/work/company')).toBe('chat');
    expect(surfaceFromHash('#/world/media-vault')).toBe('chat');
    expect(surfaceFromHash('#/modules/local-video-studio')).toBe('chat');
    expect(surfaceFromHash('#/settings/lab')).toBe('chat');
    expect(surfaceFromHash('')).toBe('chat');
  });

  it('入口文案不含已拿掉的產品面', () => {
    const blob = Object.values(SURFACE_LABEL).join('\n');
    for (const word of REMOVED) {
      expect(blob.includes(word)).toBe(false);
    }
  });
});
