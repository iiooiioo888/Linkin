import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import { id, label, Page } from '../../routes/mounts/prompt-compression.ts';
import { PROMPT_COMPRESSION_GAP } from './gap.ts';

describe('提示詞壓縮掛載', () => {
  it('匯出殼層要讀的 id、label、Page', () => {
    expect(id).toBe('prompt-compression');
    expect(label).toBe('提示詞壓縮');
    expect(typeof Page).toBe('function');
  });

  it('頁面標出缺口，並列出不能挪用的端點與內部函式', () => {
    const html = renderToStaticMarkup(createElement(Page));
    expect(html).toContain('提示詞壓縮');
    expect(html).toContain(PROMPT_COMPRESSION_GAP.status);
    expect(html).toContain(PROMPT_COMPRESSION_GAP.missing);
    expect(html).toContain(PROMPT_COMPRESSION_GAP.notThis.path);
    for (const name of PROMPT_COMPRESSION_GAP.internalOnly) {
      expect(html).toContain(name);
    }
  });

  it('不呼叫壓縮或優化管線', () => {
    const page = readFileSync(new URL('./Page.tsx', import.meta.url), 'utf8');
    const gap = readFileSync(new URL('./gap.ts', import.meta.url), 'utf8');
    const mount = readFileSync(new URL('../../routes/mounts/prompt-compression.ts', import.meta.url), 'utf8');
    const sources = `${page}\n${gap}\n${mount}`;
    expect(sources).not.toMatch(/fetch\s*\(/);
    expect(sources).not.toMatch(/labOptimizePrompt|call_llm|optimize_prompt/);
    expect(page).not.toContain('/lab/prompt/optimize');
  });
});
