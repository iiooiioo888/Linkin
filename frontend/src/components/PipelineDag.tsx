/**
 * LangGraph 管線 DAG（React Flow）— 節點與邊可視化。
 */
import { useMemo } from 'react';
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { mapPhaseToDagNodeId } from '../lib/animLive';

const BLUE = '#007AFF';
const GREEN = '#34C759';
const GRAY = '#8E8E93';

const STAGES = [
  { id: 'sense', label: '感知', x: 40, y: 80 },
  { id: 'route', label: '路由', x: 200, y: 80 },
  { id: 'gen', label: '生成', x: 360, y: 40 },
  { id: 'company', label: '公司執行', x: 360, y: 160 },
  { id: 'eval', label: '評估', x: 540, y: 80 },
  { id: 'reflect', label: '反思', x: 700, y: 40 },
  { id: 'improve', label: '改進', x: 700, y: 160 },
  { id: 'out', label: '輸出', x: 880, y: 80 },
];

const LINKS: Array<[string, string]> = [
  ['sense', 'route'],
  ['route', 'gen'],
  ['route', 'company'],
  ['gen', 'eval'],
  ['company', 'eval'],
  ['eval', 'reflect'],
  ['eval', 'out'],
  ['reflect', 'improve'],
  ['improve', 'gen'],
];

export default function PipelineDag({
  phase,
  height = 280,
}: {
  phase?: string | null;
  height?: number;
}) {
  const active = mapPhaseToDagNodeId(phase);

  const nodes: Node[] = useMemo(
    () =>
      STAGES.map((s) => {
        const hot = s.id === active;
        return {
          id: s.id,
          position: { x: s.x, y: s.y },
          data: { label: s.label },
          style: {
            borderRadius: 14,
            border: `1px solid ${hot ? BLUE : 'rgba(255,255,255,0.1)'}`,
            background: hot ? 'rgba(0,122,255,0.22)' : 'rgba(44,44,46,0.92)',
            color: hot ? '#fff' : '#F5F5F7',
            fontSize: 12,
            fontWeight: 700,
            padding: '8px 14px',
            boxShadow: hot ? `0 0 0 3px ${BLUE}33` : 'none',
            minWidth: 88,
            textAlign: 'center' as const,
          },
        };
      }),
    [active],
  );

  const edges: Edge[] = useMemo(
    () =>
      LINKS.map(([a, b], i) => {
        const hot = active === a || active === b;
        return {
          id: `e-${i}`,
          source: a,
          target: b,
          animated: hot,
          style: { stroke: hot ? BLUE : 'rgba(255,255,255,0.14)', strokeWidth: hot ? 2 : 1.2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: hot ? BLUE : GRAY, width: 14, height: 14 },
        };
      }),
    [active],
  );

  return (
    <div className="apple-card overflow-hidden" style={{ height }}>
      <div className="apple-card__head">
        <h2 className="apple-title">管線 DAG</h2>
        <span className="text-[10px] text-[#8E8E93]">{phase || 'IDLE'}</span>
      </div>
      <div className="relative min-h-0 flex-1" style={{ height: height - 44 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          minZoom={0.5}
          maxZoom={1.4}
        >
          <Background color="rgba(255,255,255,0.06)" gap={22} size={1} />
          <Controls
            showInteractive={false}
            className="!rounded-xl !border-white/10 !bg-[#2C2C2E]/90 !shadow-none"
          />
          <MiniMap
            nodeColor={(n) => (n.id === active ? BLUE : GREEN)}
            maskColor="rgba(0,0,0,0.55)"
            className="!rounded-xl !border-white/10 !bg-[#1C1C1E]/90"
          />
        </ReactFlow>
      </div>
    </div>
  );
}
