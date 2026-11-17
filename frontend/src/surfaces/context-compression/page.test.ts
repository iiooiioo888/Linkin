import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import mount, { Page, id, label } from '../../routes/mounts/context-compression';

describe('context-compression', () => {
  it('以殼約定匯出掛載', () => {
    expect(id).toBe('context-compression');
    expect(label).toBe('上下文壓縮');
    expect(typeof Page).toBe('function');
    expect(mount.id).toBe(id);
    expect(mount.label).toBe(label);
    expect(mount.Page).toBe(Page);
  });

  it('畫面可以壓縮、抽出決策、做成摘要', () => {
    const html = renderToStaticMarkup(createElement(Page));
    expect(html).toContain('上下文壓縮');
    expect(html).toContain('帶入本機對話');
    expect(html).toContain('壓縮');
    expect(html).toContain('抽出決策');
    expect(html).toContain('做成摘要');
    expect(html).toContain('data-testid="context-compression"');
    expect(html).not.toContain('尚未接上');
  });

  it('只呼叫三條薄路由，不經模型', () => {
    const page = readFileSync(new URL('./Page.tsx', import.meta.url), 'utf8');
    const client = readFileSync(new URL('../../api/client/compression.ts', import.meta.url), 'utf8');
    expect(page).not.toMatch(/fetch\s*\(/);
    expect(page).not.toMatch(/call_llm|optimize_prompt/);
    expect(client).toContain("postJson('/context/compress'");
    expect(client).toContain("postJson('/context/decisions'");
    expect(client).toContain("postJson('/context/trace-summary'");
    expect(client).not.toContain('/lab/prompt/optimize');
  });
});
