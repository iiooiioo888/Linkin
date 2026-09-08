/**
 * crypto.randomUUID polyfill：
 * 瀏覽器（Chrome/Edge）只在「安全上下文」提供 crypto.randomUUID —— 也就是
 * HTTPS 或 localhost。本服務常用 http://<IP>/ 直連，屬非安全上下文，
 * 直接呼叫會拋 "crypto.randomUUID is not a function"，導致發送鍵失效。
 *
 * getRandomValues 在所有上下文都可用，用它湊一個 v4 UUID。
 * 於 main.tsx 最早匯入，令既有 crypto.randomUUID() 呼叫無需改寫。
 */
if (typeof crypto !== 'undefined' && typeof crypto.randomUUID !== 'function') {
  const buf = new Uint8Array(16);
  (crypto as Crypto & { randomUUID?: () => string }).randomUUID = () => {
    crypto.getRandomValues(buf);
    buf[6] = (buf[6] & 0x0f) | 0x40; // version 4
    buf[8] = (buf[8] & 0x3f) | 0x80; // variant 10xx
    const hex = [...buf].map((b) => b.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  };
}

export {};
