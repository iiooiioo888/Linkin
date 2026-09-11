import './monitor.css';

export type PipelineNode = {
  id: string;
  label: string;
  timingMs?: number | null;
  state: 'done' | 'active' | 'pending';
};

export function PipelineTimeline({ nodes }: { nodes: PipelineNode[] }) {
  return (
    <div className="mon-pipeline" role="list">
      {nodes.map((node, i) => {
        const isLast = i === nodes.length - 1;
        const nextActive = !isLast && nodes[i + 1]?.state === 'active';
        const connectorDone = node.state === 'done' && (nodes[i + 1]?.state === 'done' || nodes[i + 1]?.state === 'active');
        const connectorActive = node.state === 'done' && nextActive;
        return (
          <div key={node.id} className="mon-pipeline__node" role="listitem">
            {!isLast ? (
              <div
                className={`mon-pipeline__connector${connectorActive ? ' mon-pipeline__connector--active' : connectorDone ? ' mon-pipeline__connector--done' : ''}`}
              />
            ) : null}
            <div className={`mon-pipeline__dot mon-pipeline__dot--${node.state}`}>{i + 1}</div>
            <span className="mon-pipeline__label">{node.label}</span>
            {node.timingMs != null && node.timingMs > 0 ? (
              <span className="mon-pipeline__timing">{Math.round(node.timingMs)}ms</span>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
