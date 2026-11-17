import { describe, expect, it } from 'vitest';
import mount, { Page, id, label } from '../../routes/mounts/context-compression';
import {
  GAP_LEAD,
  MISSING_COMPRESSION_APIS,
  NEARBY_ROUTES,
} from './gap';

function textOf(node: unknown): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(textOf).join('');
  if (typeof node === 'object' && 'props' in node) {
    const props = (node as { props?: { children?: unknown } }).props;
    return textOf(props?.children);
  }
  return '';
}

describe('context-compression', () => {
  it('以殼約定匯出掛載', () => {
    expect(id).toBe('context-compression');
    expect(label).toBe('上下文壓縮');
    expect(typeof Page).toBe('function');
    expect(mount.id).toBe(id);
    expect(mount.label).toBe(label);
    expect(mount.Page).toBe(Page);
  });

  it('畫面標出缺少的壓縮 API，並寫明相近路由不做壓縮', () => {
    const text = textOf(Page());
    expect(text).toContain('上下文壓縮');
    expect(text).toContain(GAP_LEAD);
    for (const name of MISSING_COMPRESSION_APIS) {
      expect(text).toContain(name);
    }
    for (const item of NEARBY_ROUTES) {
      expect(text).toContain(item.route);
      expect(text).toContain(item.does);
    }
    expect(text).not.toContain('開始壓縮');
  });
});
