/** 為尚無實拍圖的世界／道具／建築產生可進燈箱的 SVG 視覺卡。 */

function hue(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h) % 360;
}

function svgUri(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function esc(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

const RARITY_HUE: Record<string, number> = {
  common: 210,
  uncommon: 145,
  rare: 210,
  epic: 275,
  legendary: 42,
};

export function npcPortraitUri(name: string, faction: string, occupation = ''): string {
  const h = hue(faction || name);
  const initials = Array.from(name)
    .filter((ch) => ch.trim())
    .slice(0, 2)
    .join('');
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 480" width="360" height="480">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="hsl(${h},42%,18%)"/>
        <stop offset="1" stop-color="hsl(${(h + 40) % 360},48%,8%)"/>
      </linearGradient>
    </defs>
    <rect width="360" height="480" rx="28" fill="url(#g)"/>
    <circle cx="180" cy="188" r="86" fill="hsla(0,0%,100%,0.08)" stroke="hsl(${h},70%,68%)" stroke-width="3"/>
    <text x="180" y="208" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="64" font-weight="700" fill="#F5F5F7">${esc(initials || '?')}</text>
    <text x="180" y="332" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="22" font-weight="650" fill="#F5F5F7">${esc(name.slice(0, 16))}</text>
    <text x="180" y="364" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="13" fill="#AEAEB2">${esc((occupation || faction).slice(0, 22))}</text>
  </svg>`);
}

export function itemTileUri(name: string, rarity: string, type: string): string {
  const h = RARITY_HUE[rarity] ?? hue(name);
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" width="320" height="320">
    <defs>
      <radialGradient id="r" cx="50%" cy="30%" r="80%">
        <stop offset="0" stop-color="hsl(${h},70%,38%)"/>
        <stop offset="1" stop-color="hsl(${h},40%,8%)"/>
      </radialGradient>
    </defs>
    <rect width="320" height="320" rx="24" fill="#111113"/>
    <polygon points="160,36 276,108 276,212 160,284 44,212 44,108" fill="url(#r)" stroke="hsl(${h},80%,72%)" stroke-width="2.4"/>
    <text x="160" y="168" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="28" font-weight="700" fill="#F5F5F7">${esc(name.slice(0, 8))}</text>
    <text x="160" y="196" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="12" fill="#AEAEB2">${esc(rarity)} · ${esc(type)}</text>
  </svg>`);
}

export function factionBannerUri(name: string, alignment = '', creed = ''): string {
  const h = hue(name);
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" width="640" height="360">
    <defs>
      <linearGradient id="b" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="hsl(${h},46%,16%)"/>
        <stop offset="1" stop-color="hsl(${(h + 28) % 360},50%,7%)"/>
      </linearGradient>
    </defs>
    <rect width="640" height="360" rx="24" fill="url(#b)"/>
    <circle cx="92" cy="180" r="46" fill="none" stroke="hsl(${h},75%,68%)" stroke-width="3"/>
    <circle cx="92" cy="180" r="18" fill="hsl(${h},75%,68%)"/>
    <text x="168" y="160" font-family="ui-sans-serif,system-ui" font-size="32" font-weight="700" fill="#F5F5F7">${esc(name.slice(0, 18))}</text>
    <text x="168" y="192" font-family="ui-sans-serif,system-ui" font-size="14" fill="#AEAEB2">${esc(alignment.slice(0, 28))}</text>
    <text x="168" y="230" font-family="ui-sans-serif,system-ui" font-size="13" fill="#8E8E93">${esc(creed.slice(0, 42))}</text>
  </svg>`);
}

export function questCardUri(title: string, questType: string, difficulty: string): string {
  const h = questType.includes('主') ? 28 : questType.includes('日') ? 145 : 210;
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 280" width="480" height="280">
    <rect width="480" height="280" rx="22" fill="#1C1C1E"/>
    <rect x="0" y="0" width="10" height="280" fill="hsl(${h},80%,58%)"/>
    <text x="36" y="64" font-family="ui-sans-serif,system-ui" font-size="13" fill="#8E8E93">${esc(questType)} · ${esc(difficulty)}</text>
    <text x="36" y="112" font-family="ui-sans-serif,system-ui" font-size="24" font-weight="700" fill="#F5F5F7">${esc(title.slice(0, 22))}</text>
    <rect x="36" y="148" width="120" height="8" rx="4" fill="hsla(${h},70%,58%,0.45)"/>
    <rect x="36" y="168" width="200" height="8" rx="4" fill="rgba(255,255,255,0.08)"/>
    <rect x="36" y="188" width="160" height="8" rx="4" fill="rgba(255,255,255,0.06)"/>
  </svg>`);
}

export function buildingPostcardUri(input: {
  style: string;
  region?: string;
  width?: number;
  height?: number;
  length?: number;
}): string {
  const h = hue(input.style + (input.region ?? ''));
  const w = Math.max(2, Math.min(8, Math.round((input.width ?? 8) / 8)));
  const d = Math.max(2, Math.min(8, Math.round((input.length ?? 8) / 8)));
  const cubes: string[] = [];
  for (let z = 0; z < d; z += 1) {
    for (let x = 0; x < w; x += 1) {
      const px = 170 + x * 22 - z * 18;
      const py = 168 + z * 12 - x * 4;
      cubes.push(
        `<g transform="translate(${px},${py})">
          <polygon points="0,8 16,0 32,8 16,16" fill="hsl(${h},45%,${38 - z * 2}%)"/>
          <polygon points="0,8 16,16 16,32 0,24" fill="hsl(${h},40%,22%)"/>
          <polygon points="16,16 32,8 32,24 16,32" fill="hsl(${h},55%,16%)"/>
        </g>`,
      );
    }
  }
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 300" width="480" height="300">
    <rect width="480" height="300" rx="22" fill="#111113"/>
    ${cubes.join('')}
    <text x="24" y="40" font-family="ui-sans-serif,system-ui" font-size="18" font-weight="700" fill="#F5F5F7">${esc(input.style.slice(0, 18))}</text>
    <text x="24" y="64" font-family="ui-sans-serif,system-ui" font-size="12" fill="#8E8E93">${esc((input.region ?? '').slice(0, 20))}</text>
  </svg>`);
}

function wrapLines(text: string, width: number, maxLines: number): string[] {
  const words = text.replace(/\s+/g, ' ').trim().split(' ');
  const lines: string[] = [];
  let current = '';
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > width) {
      if (current) lines.push(current);
      current = word;
      if (lines.length >= maxLines) break;
    } else {
      current = next;
    }
  }
  if (current && lines.length < maxLines) lines.push(current);
  return lines;
}

export function agentPortraitUri(name: string, level: number, category = ''): string {
  const h = hue(category || name);
  const initials = Array.from(name)
    .filter((ch) => ch.trim())
    .slice(0, 2)
    .join('');
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" width="240" height="240">
    <rect width="240" height="240" rx="28" fill="hsl(${h},38%,12%)"/>
    <circle cx="120" cy="108" r="54" fill="hsla(0,0%,100%,0.07)" stroke="hsl(${h},70%,62%)" stroke-width="3"/>
    <text x="120" y="122" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="42" font-weight="700" fill="#F5F5F7">${esc(initials || '?')}</text>
    <text x="120" y="188" text-anchor="middle" font-family="ui-sans-serif,system-ui" font-size="13" font-weight="650" fill="#AEAEB2">L${level} · ${esc(name.slice(0, 12))}</text>
  </svg>`);
}

export function memoryTileUri(text: string, score?: number | string): string {
  const h = hue(text.slice(0, 24));
  const lines = wrapLines(text, 28, 5);
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 280" width="420" height="280">
    <rect width="420" height="280" rx="22" fill="#1C1C1E"/>
    <rect x="0" y="0" width="8" height="280" fill="hsl(${h},72%,52%)"/>
    <text x="28" y="42" font-family="ui-sans-serif,system-ui" font-size="12" fill="#8E8E93">記憶${score != null && score !== '' ? ` · ${esc(String(score))}` : ''}</text>
    ${lines.map((line, i) => `<text x="28" y="${84 + i * 28}" font-family="ui-sans-serif,system-ui" font-size="16" fill="#F5F5F7">${esc(line)}</text>`).join('')}
  </svg>`);
}

export function schoolBannerUri(name: string, domain = ''): string {
  const h = hue(name);
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 260" width="480" height="260">
    <defs>
      <linearGradient id="s" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="hsl(${h},50%,16%)"/>
        <stop offset="1" stop-color="hsl(${(h + 48) % 360},42%,8%)"/>
      </linearGradient>
    </defs>
    <rect width="480" height="260" rx="22" fill="url(#s)"/>
    <circle cx="72" cy="130" r="28" fill="none" stroke="hsl(${h},80%,68%)" stroke-width="2.4"/>
    <text x="120" y="122" font-family="ui-sans-serif,system-ui" font-size="24" font-weight="700" fill="#F5F5F7">${esc(name.slice(0, 16))}</text>
    <text x="120" y="154" font-family="ui-sans-serif,system-ui" font-size="13" fill="#AEAEB2">${esc(domain.slice(0, 28))}</text>
  </svg>`);
}

export function eventCardUri(title: string, kind = ''): string {
  const h = hue(kind || title);
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 240" width="480" height="240">
    <rect width="480" height="240" rx="20" fill="#141416"/>
    <rect x="24" y="24" width="64" height="8" rx="4" fill="hsl(${h},80%,58%)"/>
    <text x="24" y="72" font-family="ui-sans-serif,system-ui" font-size="12" fill="#8E8E93">${esc(kind.slice(0, 18) || '事件')}</text>
    <text x="24" y="112" font-family="ui-sans-serif,system-ui" font-size="22" font-weight="700" fill="#F5F5F7">${esc(title.slice(0, 20))}</text>
    <rect x="24" y="148" width="180" height="8" rx="4" fill="rgba(255,255,255,0.08)"/>
    <rect x="24" y="168" width="120" height="8" rx="4" fill="rgba(255,255,255,0.05)"/>
  </svg>`);
}

export function promptSnapshotUri(title: string, body: string, tone: 'before' | 'after' = 'before'): string {
  const h = tone === 'after' ? 145 : 210;
  const lines = wrapLines(body, 34, 8);
  return svgUri(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 420" width="640" height="420">
    <rect width="640" height="420" rx="24" fill="#111113"/>
    <rect x="0" y="0" width="640" height="48" fill="hsl(${h},42%,14%)"/>
    <text x="24" y="32" font-family="ui-sans-serif,system-ui" font-size="14" font-weight="700" fill="hsl(${h},80%,72%)">${esc(title)}</text>
    ${lines.map((line, i) => `<text x="28" y="${88 + i * 34}" font-family="ui-sans-serif,system-ui" font-size="16" fill="#F5F5F7">${esc(line)}</text>`).join('')}
  </svg>`);
}

export function extractMarkdownImages(markdown: string, baseUrl?: string): Array<{ src: string; caption: string }> {
  const found = new Map<string, string>();
  const push = (src: string, caption: string) => {
    const trimmed = src.trim();
    if (!trimmed || trimmed.startsWith('data:')) {
      if (trimmed.startsWith('data:image')) found.set(trimmed, caption);
      return;
    }
    try {
      const abs = new URL(trimmed, baseUrl || (typeof window !== 'undefined' ? window.location.href : 'https://local.invalid')).href;
      if (/^https?:/i.test(abs) || abs.startsWith('data:image')) found.set(abs, caption || found.get(abs) || '');
    } catch {
      /* ignore */
    }
  };
  const md = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)/g;
  let match: RegExpExecArray | null;
  while ((match = md.exec(markdown))) {
    push(match[2], match[3] || match[1] || '');
  }
  const html = /<img[^>]+src=["']([^"']+)["'][^>]*>/gi;
  while ((match = html.exec(markdown))) {
    const alt = /alt=["']([^"']*)["']/i.exec(match[0]);
    push(match[1], alt?.[1] ?? '');
  }
  return [...found.entries()].map(([src, caption]) => ({ src, caption }));
}
