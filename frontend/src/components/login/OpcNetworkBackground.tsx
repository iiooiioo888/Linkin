import { useEffect, useRef } from 'react';

type Tier = 'l4' | 'l3' | 'l2';
type Shape = 'diamond' | 'triangle' | 'circle';

interface Node {
  x: number;
  y: number;
  tier: Tier;
  shape: Shape;
  phase: number;
  r: number;
}

interface Link {
  a: number;
  b: number;
  tier: 'gold' | 'blue';
  inquiry?: boolean;
}

interface Packet {
  link: number;
  t: number;
  speed: number;
}

const COLORS = {
  bg: '#0a0a0d',
  gold: '#c9a961',
  blue: '#7a92b8',
  cyan: '#5fb8c9',
  red: '#c47a7a',
  line: '#22222a',
  faint: '#4a4a54',
};

function tierColor(tier: Tier): string {
  if (tier === 'l4') return COLORS.gold;
  if (tier === 'l3') return COLORS.blue;
  return COLORS.cyan;
}

function nodeCount(reduced: boolean, mobile: boolean): number {
  if (reduced) return 12;
  if (mobile) return 18;
  return 28;
}

function buildNetwork(w: number, h: number, count: number): { nodes: Node[]; links: Link[] } {
  const nodes: Node[] = [];
  const tiers: Tier[] = ['l4', 'l3', 'l2'];
  const shapes: Record<Tier, Shape> = { l4: 'diamond', l3: 'triangle', l2: 'circle' };
  const yBands: Record<Tier, number> = { l4: 0.18, l3: 0.48, l2: 0.78 };

  for (let i = 0; i < count; i++) {
    const tier = tiers[i % 3];
    const band = yBands[tier];
    nodes.push({
      x: ((i * 73 + 17) % 100) / 100 * w,
      y: band * h + (((i * 41) % 100) / 100 - 0.5) * h * 0.22,
      tier,
      shape: shapes[tier],
      phase: (i * 0.7) % (Math.PI * 2),
      r: tier === 'l4' ? 5 : tier === 'l3' ? 4 : 3,
    });
  }

  const links: Link[] = [];
  for (let i = 0; i < nodes.length; i++) {
    const ni = nodes[i];
    let best = -1;
    let bestD = Infinity;
    for (let j = 0; j < nodes.length; j++) {
      if (i === j) continue;
      const nj = nodes[j];
      const tierOrder = { l4: 0, l3: 1, l2: 2 };
      if (tierOrder[nj.tier] <= tierOrder[ni.tier]) continue;
      const dx = ni.x - nj.x;
      const dy = ni.y - nj.y;
      const d = dx * dx + dy * dy;
      if (d < bestD) {
        bestD = d;
        best = j;
      }
    }
    if (best >= 0) {
      links.push({
        a: i,
        b: best,
        tier: ni.tier === 'l4' ? 'gold' : 'blue',
        inquiry: Math.random() < 0.08,
      });
    }
  }
  return { nodes, links };
}

function drawDiamond(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string) {
  ctx.save();
  ctx.translate(x, y);
  ctx.rotate(Math.PI / 4);
  ctx.fillStyle = color;
  ctx.fillRect(-r, -r, r * 2, r * 2);
  ctx.restore();
}

function drawTriangle(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string) {
  ctx.beginPath();
  ctx.moveTo(x, y - r);
  ctx.lineTo(x + r, y + r * 0.8);
  ctx.lineTo(x - r, y + r * 0.8);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
}

function drawNode(ctx: CanvasRenderingContext2D, node: Node, pulse: number) {
  const alpha = 0.55 + Math.sin(pulse + node.phase) * 0.2;
  const color = tierColor(node.tier);
  ctx.globalAlpha = alpha;
  if (node.shape === 'diamond') drawDiamond(ctx, node.x, node.y, node.r, color);
  else if (node.shape === 'triangle') drawTriangle(ctx, node.x, node.y, node.r, color);
  else {
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

function bezierPath(
  ax: number,
  ay: number,
  bx: number,
  by: number,
): { cp1x: number; cp1y: number; cp2x: number; cp2y: number } {
  const dx = bx - ax;
  const dy = by - ay;
  return {
    cp1x: ax + dx * 0.25,
    cp1y: ay - Math.abs(dy) * 0.3,
    cp2x: bx - dx * 0.25,
    cp2y: by + Math.abs(dy) * 0.15,
  };
}

function pointOnBezier(
  ax: number,
  ay: number,
  cp1x: number,
  cp1y: number,
  cp2x: number,
  cp2y: number,
  bx: number,
  by: number,
  t: number,
): [number, number] {
  const u = 1 - t;
  const x = u * u * u * ax + 3 * u * u * t * cp1x + 3 * u * t * t * cp2x + t * t * t * bx;
  const y = u * u * u * ay + 3 * u * u * t * cp1y + 3 * u * t * t * cp2y + t * t * t * by;
  return [x, y];
}

export default function OpcNetworkBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const mobile = window.innerWidth < 640;
    const lowCores = typeof navigator.hardwareConcurrency === 'number' && navigator.hardwareConcurrency <= 4;
    const lite = mobile || lowCores;
    const count = nodeCount(reduced, lite);

    let w = 0;
    let h = 0;
    let nodes: Node[] = [];
    let links: Link[] = [];
    let packets: Packet[] = [];
    let raf = 0;
    let start = performance.now();
    let inquiryRing = { x: 0, y: 0, r: 0, life: 0 };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, lite ? 1.5 : 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const net = buildNetwork(w, h, count);
      nodes = net.nodes;
      links = net.links;
      packets = links.slice(0, lite ? 6 : 12).map((_, i) => ({
        link: i % links.length,
        t: Math.random(),
        speed: 0.0008 + Math.random() * 0.0012,
      }));
    };

    resize();
    window.addEventListener('resize', resize);

    const draw = (now: number) => {
      const elapsed = (now - start) / 1000;
      ctx.fillStyle = COLORS.bg;
      ctx.fillRect(0, 0, w, h);

      // 淡網格
      ctx.strokeStyle = COLORS.line;
      ctx.lineWidth = 0.5;
      ctx.globalAlpha = 0.35;
      const grid = lite ? 80 : 60;
      for (let x = 0; x < w; x += grid) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y < h; y += grid) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      for (const link of links) {
        const a = nodes[link.a];
        const b = nodes[link.b];
        const { cp1x, cp1y, cp2x, cp2y } = bezierPath(a.x, a.y, b.x, b.y);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, b.x, b.y);
        ctx.strokeStyle = link.tier === 'gold' ? COLORS.gold : COLORS.blue;
        ctx.globalAlpha = link.inquiry ? 0.35 : 0.22;
        ctx.lineWidth = link.inquiry ? 1 : 0.75;
        if (link.inquiry) ctx.setLineDash([4, 6]);
        else ctx.setLineDash([]);
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }

      if (!reduced) {
        for (const pkt of packets) {
          const link = links[pkt.link];
          if (!link) continue;
          const a = nodes[link.a];
          const b = nodes[link.b];
          const { cp1x, cp1y, cp2x, cp2y } = bezierPath(a.x, a.y, b.x, b.y);
          pkt.t += pkt.speed;
          if (pkt.t > 1) pkt.t = 0;
          const [px, py] = pointOnBezier(a.x, a.y, cp1x, cp1y, cp2x, cp2y, b.x, b.y, pkt.t);
          ctx.beginPath();
          ctx.arc(px, py, 2, 0, Math.PI * 2);
          ctx.fillStyle = link.tier === 'gold' ? COLORS.gold : COLORS.cyan;
          ctx.globalAlpha = 0.85;
          ctx.fill();
          ctx.globalAlpha = 1;
        }

        if (inquiryRing.life <= 0 && Math.random() < 0.003) {
          const n = nodes[Math.floor(Math.random() * nodes.length)];
          inquiryRing = { x: n.x, y: n.y, r: 8, life: 1 };
        }
        if (inquiryRing.life > 0) {
          ctx.beginPath();
          ctx.arc(inquiryRing.x, inquiryRing.y, inquiryRing.r, 0, Math.PI * 2);
          ctx.strokeStyle = COLORS.red;
          ctx.globalAlpha = inquiryRing.life * 0.5;
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 5]);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.globalAlpha = 1;
          inquiryRing.r += 0.6;
          inquiryRing.life -= 0.012;
        }
      }

      const pulse = reduced ? 0 : elapsed * 2;
      for (const node of nodes) drawNode(ctx, node, pulse);

      if (!reduced) raf = requestAnimationFrame(draw);
    };

    if (reduced) draw(performance.now());
    else raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return <canvas ref={canvasRef} className="login-bg-canvas" aria-hidden="true" />;
}
