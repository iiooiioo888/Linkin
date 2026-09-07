/**
 * Archify 檢視器 — architecture / workflow / data-flow / lifecycle IR → SVG。
 * 對齊 tt-a1i/archify：確定性佈局、可聚焦節點、不發明拓撲。
 */
import { useId, useMemo } from 'react';
import type { ArchifyEdge, ArchifyIR, ArchifyLane, ArchifyNode } from '../api/client';

export type { ArchifyIR, ArchifyNode, ArchifyEdge };

const ROLE_LAYER: Record<string, number> = {
  external: 0,
  data: 1,
  service: 2,
  api: 3,
  frontend: 4,
};

const STATUS_COLOR: Record<string, string> = {
  hub: '#007AFF',
  wired: '#34C759',
  catalog: '#8E8E93',
};

const ROLE_COLOR: Record<string, string> = {
  frontend: '#007AFF',
  api: '#5856D6',
  service: '#34C759',
  data: '#FF9500',
  external: '#FF2D55',
};

type Pos = { x: number; y: number; w: number; h: number };

function nodeColor(node: ArchifyNode): string {
  if (node.status && STATUS_COLOR[node.status]) return STATUS_COLOR[node.status];
  return ROLE_COLOR[node.role ?? 'service'] ?? ROLE_COLOR.service;
}

function isLtr(ir: ArchifyIR): boolean {
  const kind = ir.meta?.type ?? 'architecture';
  return kind === 'workflow' || kind === 'data-flow' || kind === 'lifecycle';
}

function layoutArchitecture(nodes: ArchifyNode[], compact: boolean): Map<string, Pos> {
  const layers: ArchifyNode[][] = [[], [], [], [], []];
  for (const node of nodes) {
    const idx = ROLE_LAYER[node.role ?? 'service'] ?? 2;
    layers[idx].push(node);
  }
  const used = layers.filter((row) => row.length > 0);
  const nmax = Math.max(1, ...used.map((row) => row.length));
  const nodeW = compact || nmax > 12 ? 108 : 132;
  const nodeH = compact || nmax > 12 ? 38 : 46;
  const gapX = 18;
  const gapY = 64;
  const maxCols = nmax > 24 ? 8 : nmax > 12 ? 6 : Math.max(3, nmax);
  const positions = new Map<string, Pos>();
  let y = 36;
  for (const layer of used) {
    const cols = Math.min(maxCols, layer.length);
    const rows = Math.ceil(layer.length / cols);
    layer.forEach((node, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const rowCount = row === rows - 1 ? layer.length - row * cols : cols;
      const rowW = rowCount * nodeW + (rowCount - 1) * gapX;
      const originX = 36 + Math.max(0, (cols * nodeW + (cols - 1) * gapX - rowW) / 2);
      positions.set(node.id, {
        x: originX + col * (nodeW + gapX),
        y: y + row * (nodeH + 14),
        w: nodeW,
        h: nodeH,
      });
    });
    y += rows * (nodeH + 14) + gapY - 14;
  }
  return positions;
}

function layoutLanes(nodes: ArchifyNode[], lanes: ArchifyLane[], compact: boolean): Map<string, Pos> {
  const nodeW = compact ? 108 : 128;
  const nodeH = compact ? 38 : 44;
  const gapX = 56;
  const gapY = 16;
  const byLane = new Map<string, ArchifyNode[]>();
  for (const lane of lanes) byLane.set(lane.id, []);
  for (const node of nodes) {
    const key = node.lane && byLane.has(node.lane) ? node.lane : (lanes[0]?.id ?? 'default');
    if (!byLane.has(key)) byLane.set(key, []);
    byLane.get(key)!.push(node);
  }
  const positions = new Map<string, Pos>();
  const colIds = lanes.length ? lanes.map((l) => l.id) : [...byLane.keys()];
  colIds.forEach((laneId, col) => {
    const colNodes = byLane.get(laneId) ?? [];
    colNodes.forEach((node, row) => {
      positions.set(node.id, {
        x: 28 + col * (nodeW + gapX),
        y: 48 + row * (nodeH + gapY),
        w: nodeW,
        h: nodeH,
      });
    });
  });
  return positions;
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function edgePath(from: Pos, to: Pos, ltr: boolean): string {
  if (ltr) {
    const x1 = from.x + from.w;
    const y1 = from.y + from.h / 2;
    const x2 = to.x;
    const y2 = to.y + to.h / 2;
    const mx = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
  }
  const x1 = from.x + from.w / 2;
  const y1 = from.y + from.h;
  const x2 = to.x + to.w / 2;
  const y2 = to.y;
  const my = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
}

export default function ArchifyViewer({
  ir,
  focusId,
  onSelect,
  compact = false,
}: {
  ir: ArchifyIR;
  focusId?: string | null;
  onSelect?: (id: string) => void;
  compact?: boolean;
}) {
  const markerId = useId().replace(/:/g, '');
  const ltr = isLtr(ir);
  const many = ir.nodes.length > 16;
  const positions = useMemo(() => {
    if (ltr && ir.lanes && ir.lanes.length > 0) return layoutLanes(ir.nodes, ir.lanes, compact || many);
    if (ltr) return layoutLanes(ir.nodes, inferLanes(ir.nodes), compact || many);
    return layoutArchitecture(ir.nodes, compact || many);
  }, [compact, ir.lanes, ir.nodes, ltr, many]);

  const posList = [...positions.values()];
  const width = Math.max(320, ...posList.map((p) => p.x + p.w + 24), 1);
  const height = Math.max(180, ...posList.map((p) => p.y + p.h + 24), 1);
  const title = ir.meta?.title ?? '架構圖';
  const kind = ir.meta?.type ?? 'architecture';

  if (!ir.nodes.length) {
    return (
      <div className="apple-card overflow-hidden">
        <div className="apple-card__head">
          <h2 className="apple-title">{title}</h2>
        </div>
        <p className="px-4 py-8 text-center text-[11px] text-[#636366]">沒有節點</p>
      </div>
    );
  }

  return (
    <div className="apple-card overflow-hidden">
      <div className="apple-card__head">
        <h2 className="apple-title">{title}</h2>
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#8E8E93]">
          Archify · {kind}
        </span>
      </div>
      <div className="apple-card__body apple-card__body--static overflow-x-auto p-2">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="min-w-full"
          role="img"
          aria-label={title}
        >
          <defs>
            <marker
              id={`archify-arrow-${markerId}`}
              markerWidth="8"
              markerHeight="8"
              refX="6"
              refY="3"
              orient="auto"
            >
              <path d="M0,0 L6,3 L0,6 Z" fill="rgba(174,174,178,0.9)" />
            </marker>
          </defs>
          {ltr && ir.lanes
            ? ir.lanes.map((lane) => {
                const sample = ir.nodes.find((n) => n.lane === lane.id);
                const pos = sample ? positions.get(sample.id) : undefined;
                if (!pos) return null;
                return (
                  <text
                    key={lane.id}
                    x={pos.x + pos.w / 2}
                    y="22"
                    textAnchor="middle"
                    fill="#636366"
                    fontSize="10"
                    fontWeight="700"
                  >
                    {lane.label}
                  </text>
                );
              })
            : null}
          {ir.edges.map((edge, i) => {
            const from = positions.get(edge.from);
            const to = positions.get(edge.to);
            if (!from || !to) return null;
            const focused =
              focusId && (edge.from === focusId || edge.to === focusId);
            const d = edgePath(from, to, ltr);
            const mid = ltr
              ? { x: (from.x + from.w + to.x) / 2, y: (from.y + to.y) / 2 }
              : { x: (from.x + to.x) / 2, y: (from.y + from.h + to.y) / 2 };
            return (
              <g key={`${edge.from}-${edge.to}-${i}`}>
                <path
                  d={d}
                  fill="none"
                  stroke={focused ? 'rgba(10,132,255,0.85)' : 'rgba(255,255,255,0.18)'}
                  strokeWidth={focused ? 1.8 : 1.2}
                  markerEnd={`url(#archify-arrow-${markerId})`}
                />
                {edge.label ? (
                  <text x={mid.x} y={mid.y - 4} textAnchor="middle" fill="#8E8E93" fontSize="9">
                    {edge.label}
                  </text>
                ) : null}
              </g>
            );
          })}
          {ir.nodes.map((node) => {
            const pos = positions.get(node.id);
            if (!pos) return null;
            const color = nodeColor(node);
            const on = focusId === node.id;
            const clickable = Boolean(onSelect);
            const maxChars = pos.w > 120 ? 14 : 11;
            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                onClick={clickable ? () => onSelect?.(node.id) : undefined}
                style={{ cursor: clickable ? 'pointer' : 'default' }}
              >
                <rect
                  x="0"
                  y="0"
                  width={pos.w}
                  height={pos.h}
                  rx="10"
                  fill={on ? 'rgba(10,132,255,0.18)' : 'rgba(28,28,30,0.95)'}
                  stroke={on ? '#0A84FF' : color}
                  strokeWidth={on ? 1.8 : 1.2}
                />
                <circle cx="12" cy={pos.h / 2} r="4" fill={color} />
                <text x="22" y={pos.h / 2 - 2} fill="#F5F5F7" fontSize="10" fontWeight="600">
                  {truncate(node.label, maxChars)}
                </text>
                <text x="22" y={pos.h / 2 + 12} fill="#636366" fontSize="8">
                  {node.status || node.role || 'node'}
                </text>
                <title>{[node.label, node.detail, node.id].filter(Boolean).join(' · ')}</title>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function inferLanes(nodes: ArchifyNode[]): ArchifyLane[] {
  const seen: string[] = [];
  for (const node of nodes) {
    const key = node.lane || node.role || 'node';
    if (!seen.includes(key)) seen.push(key);
  }
  return seen.map((id) => ({ id, label: id }));
}
