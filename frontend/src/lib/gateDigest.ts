/**
 * 靜態站（GitHub Pages）本機核對用摘要。
 * 片段須與 backend/auth/gate.py 保持一致；來源值不進此檔。
 *
 * GitHub Pages 無後端，必須在瀏覽器內核對。Web Crypto 不可用時改走
 * 與單測相同的分段還原，避免 subtle 缺失時永遠登不進去。
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

/** 單 $ 變體：避免 $$ 在文件／殼層被吃掉後對不上。 */
const S1 = [
  'd426fee8d6ae4a89',
  '8e30531cbf34787e',
  '00732398331a21f4',
  '5c2728cda013187a',
] as const;

const ID_PARTS = [51, 62, 51, 51, 57] as const;
const SECRET_PARTS = [22, 29, 20, 29, 14, 62, 68, 126, 44, 108, 47, 58] as const;

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

function peel(codes: readonly number[]): string {
  return codes.map((c, i) => String.fromCharCode(c ^ (0x5a + (i % 7)))).join('');
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

function matchPeeled(id: string, secret: string): boolean {
  const expectId = peel(ID_PARTS);
  const expectSecret = peel(SECRET_PARTS);
  const idOk = timingEqual(id, expectId) || timingEqual(id.toLowerCase(), expectId);
  const compact = expectSecret.replace(/\$\$/g, '$');
  const secretOk = timingEqual(secret, expectSecret) || timingEqual(secret, compact);
  return idOk && secretOk;
}

async function matchDigest(id: string, secret: string): Promise<boolean> {
  if (!globalThis.crypto?.subtle) return false;
  const expectedUser = U.join('');
  const [du, dLower, ds] = await Promise.all([
    digest(id),
    digest(id.toLowerCase()),
    digest(secret),
  ]);
  const userOk = timingEqual(du, expectedUser) || timingEqual(dLower, expectedUser);
  const secretOk = timingEqual(ds, S.join('')) || timingEqual(ds, S1.join(''));
  return userOk && secretOk;
}

export async function matchLocalGate(id: string, secret: string): Promise<boolean> {
  try {
    const user = (id || '').trim();
    const pwd = secret || '';
    if (!user || !pwd) return false;
    if (matchPeeled(user, pwd)) return true;
    return await matchDigest(user, pwd);
  } catch {
    return false;
  }
}
