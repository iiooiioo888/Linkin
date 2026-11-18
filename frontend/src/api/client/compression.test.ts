import { describe, expect, it, vi } from 'vitest';
import { boundedLimit, compressContext, readWholeNumber, truncatePrompt } from './compression';

describe('compression client', () => {
  it('reads a blank limit as the server default', () => {
    expect(readWholeNumber('')).toEqual({ ok: true, value: undefined });
    expect(readWholeNumber(' 720 ')).toEqual({ ok: true, value: 720 });
    expect(readWholeNumber('12.5').ok).toBe(false);
    expect(boundedLimit('16', { min: 17, max: 100 })).toEqual({
      ok: false,
      message: '上限要在 17 到 100 之間。',
    });
  });

  it('posts context text to the compress route', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ text: '短', original_chars: 2, result_chars: 1, helper: 'compress' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    await compressContext('原文', 80);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/context/compress');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ text: '原文', limit: 80 });
    vi.unstubAllGlobals();
  });

  it('omits the prompt limit when the field is blank', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({ text: '短', original_chars: 1, result_chars: 1, helper: 'truncate' }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    await truncatePrompt('短');
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/prompts/truncate');
    expect(JSON.parse(String(init.body))).toEqual({ text: '短' });
    vi.unstubAllGlobals();
  });
});
