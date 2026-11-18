import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { id, label, Page } from '../../routes/mounts/prompt-compression.ts';

describe('提示詞壓縮掛載', () => {
  it('匯出殼層要讀的 id、label、Page', () => {
    expect(id).toBe('prompt-compression');
    expect(label).toBe('提示詞壓縮');
    expect(typeof Page).toBe('function');
  });

  it('畫面可以送出提示詞並顯示結果位置', () => {
    const html = renderToStaticMarkup(createElement(Page));
    expect(html).toContain('提示詞壓縮');
    expect(html).toContain('不經模型');
    expect(html).toContain('>壓縮<');
    expect(html).toContain('data-testid="prompt-compression"');
    expect(html).not.toContain('尚未接上');
    expect(html).not.toContain('缺口');
  });

  it('只打截斷路由，不呼叫優化', () => {
    const page = readFileSync(new URL('./Page.tsx', import.meta.url), 'utf8');
    const mount = readFileSync(new URL('../../routes/mounts/prompt-compression.ts', import.meta.url), 'utf8');
    const client = readFileSync(new URL('../../api/client/compression.ts', import.meta.url), 'utf8');
    const sources = `${page}\n${mount}`;
    expect(sources).not.toMatch(/fetch\s*\(/);
    expect(sources).not.toMatch(/labOptimizePrompt|call_llm|optimize_prompt/);
    expect(page).not.toContain('/lab/prompt/optimize');
    expect(client).toContain("postJson('/prompts/truncate'");
    expect(client).not.toContain('/lab/prompt/optimize');
  });
});
