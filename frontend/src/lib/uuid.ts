/**
 * UUID v4 產生器（安全上下文降級兼容）。
 *
 * `crypto.randomUUID()` 僅在 secure context（HTTPS／localhost）可用；
 * 生產以 http://IP 部署時瀏覽器不提供該 API，直接呼叫會讓 React 首次
 * 渲染崩潰（白屏）。`crypto.getRandomValues` 不受此限制，用作降級熵源。
 */
export function uuidv4(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant 10xx
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
