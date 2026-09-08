/**
 * 靜態站（GitHub Pages）本機核對用摘要。
 * 片段須與 backend/auth/gate.py 保持一致；來源值不進此檔。
 */
const PEPPER = Uint8Array.from([0x6c, 0x6b, 0x6e, 0x2e, 0x67, 0x61, 0x74, 0x65]);

const U = [
  '1f4ac7b757bc42f0',
  '2bafcc236d647a3a',
  '9a11ea1ab69bf25d',
  '77ad23899d26590d',
] as const;

const S = [
  '9a9e35eac9af48e1',
  '4efc7d0d21cbd2ff',
  'e7cc4ec72c0241b3',
  '8bd13f69e5463467',
] as const;

function hexFromBuffer(buf: ArrayBuffer): string {
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function timingEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

async function digest(value: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw',
    PEPPER,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign'],
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value));
  return hexFromBuffer(sig);
}

export async function matchLocalGate(id: string, secret: string): Promise<boolean> {
  if (!globalThis.crypto?.subtle) return false;
  const user = (id || '').trim();
  const [du, ds] = await Promise.all([digest(user), digest(secret || '')]);
  const userOk = timingEqual(du, U.join(''));
  const secretOk = timingEqual(ds, S.join(''));
  return userOk && secretOk;
}
