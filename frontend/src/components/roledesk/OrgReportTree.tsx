/**
 * 組織回報鏈：上級／本角色／直屬／跳層節點與可委派提示。
 */

import { Fragment, useMemo } from 'react';
import type { RoleAgent } from '../../types';
import { agentRahoLabel, orgLevelCaption, RAHO_LAYERS } from '../../lib/rahoUi';
import { roleLabel } from '../TaskPanel';

function isLive(agent: RoleAgent): boolean {
  return agent.status === 'busy' || agent.status === 'waiting';
}

function OrgNode({
  agent,
  current,
  onOpen,
}: {
  agent: RoleAgent;
  current?: boolean;
  onOpen: (id: string) => void;
}) {
  return (
    <button
      type="button"
      className={`rd-onode ${current ? 'cur' : ''}`}
      title={`${agentRahoLabel(agent)} · ${agent.name}`}
      onClick={() => onOpen(agent.id)}
    >
      <span className={`rd-od ${isLive(agent) ? 'on' : 'off'}`} />
      <span className="rd-onode-name">{agent.name}</span>
      {current ? <small>本角色</small> : null}
    </button>
  );
}

function preferLive(agents: RoleAgent[]): RoleAgent[] {
  return [...agents].sort((a, b) => {
    const live = Number(isLive(b)) - Number(isLive(a));
    if (live) return live;
    if (a.level !== b.level) return a.level - b.level;
    return a.name.localeCompare(b.name, 'zh-Hant');
  });
}

function ancestorChain(agent: RoleAgent, byId: Map<string, RoleAgent>): RoleAgent[] {
  const chain: RoleAgent[] = [];
  const seen = new Set<string>([agent.id]);
  let cursor: RoleAgent | undefined = agent;
  while (cursor?.reporting_to) {
    const parent = byId.get(cursor.reporting_to);
    if (!parent || seen.has(parent.id)) break;
    seen.add(parent.id);
    chain.unshift(parent);
    cursor = parent;
  }
  return chain;
}

function childrenOf(id: string, agents: RoleAgent[], byId: Map<string, RoleAgent>): RoleAgent[] {
  const seen = new Set<string>();
  const out: RoleAgent[] = [];
  const push = (item: RoleAgent | undefined) => {
    if (!item || item.id === id || seen.has(item.id)) return;
    seen.add(item.id);
    out.push(item);
  };
  for (const childId of byId.get(id)?.direct_reports ?? []) push(byId.get(childId));
  for (const item of agents) {
    if (item.reporting_to === id) push(item);
  }
  return preferLive(out);
}

const MAX_PER_LAYER = 8;

type OrgLayer = { key: string; label: string; nodes: RoleAgent[]; extra: number };

function layerLabel(nodes: RoleAgent[]): string {
  const raho = [...new Set(nodes.map((node) => node.raho_layer).filter((n): n is number => typeof n === 'number'))];
  if (raho.length === 1) return RAHO_LAYERS[raho[0]]?.short ?? `L${raho[0]}`;
  const levels = [...new Set(nodes.map((node) => node.level))].sort((a, b) => a - b);
  if (levels.length === 1) return nodes[0]?.level_label || `組織 ${levels[0]}`;
  return `${nodes[0]?.level_label || '組織'} 等`;
}

function takeLayer(key: string, nodes: RoleAgent[]): OrgLayer {
  return {
    key,
    label: layerLabel(nodes),
    nodes: nodes.slice(0, MAX_PER_LAYER),
    extra: Math.max(0, nodes.length - MAX_PER_LAYER),
  };
}

function orgLayers(agent: RoleAgent, agents: RoleAgent[]): OrgLayer[] {
  const byId = new Map(agents.map((item) => [item.id, item]));
  const layers: OrgLayer[] = [
    ...ancestorChain(agent, byId).map((node) => ({
      key: `up-${node.id}`,
      label: node.raho_short || orgLevelCaption(node),
      nodes: [node],
      extra: 0,
    })),
    { key: `cur-${agent.id}`, label: agent.raho_short || orgLevelCaption(agent), nodes: [agent], extra: 0 },
  ];
  const reports = childrenOf(agent.id, agents, byId);
  if (!reports.length) return layers;
  const down = takeLayer(`down-${agent.id}`, reports);
  layers.push(down);

  const seen = new Set([agent.id, ...down.nodes.map((item) => item.id)]);
  const uniqueGrand: RoleAgent[] = [];
  for (const item of preferLive(down.nodes.flatMap((node) => childrenOf(node.id, agents, byId)))) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    uniqueGrand.push(item);
  }
  if (uniqueGrand.length) layers.push(takeLayer(`skip-${agent.id}`, uniqueGrand));
  return layers;
}

export function OrgReportTree({
  agent,
  agents,
  onOpen,
}: {
  agent: RoleAgent;
  agents: RoleAgent[];
  onOpen: (id: string) => void;
}) {
  const layers = useMemo(() => orgLayers(agent, agents), [agent, agents]);
  const canDelegate = agent.can_delegate_to ?? [];
  const reportsHere = agents.filter((item) => item.reporting_to === agent.id || (agent.direct_reports ?? []).includes(item.id)).length;
  const missing = (agent.direct_reports ?? []).filter(
    (id) =>
      id !== agent.id &&
      !id.startsWith('custom_linkin_') &&
      !agents.some((item) => item.id === id),
  ).length;

  return (
    <div className="rd-sec">
      <div className="rd-tt">組織回報鏈</div>
      <div className="rd-tree">
        {layers.map((layer, idx) => (
          <Fragment key={layer.key}>
            {idx > 0 ? <div className="rd-tree-conn" aria-hidden /> : null}
            <div className="rd-tree-row">
              <span className="rd-tree-lvl">{layer.label}</span>
              <div className="rd-tree-nodes">
                {layer.nodes.map((node) => (
                  <OrgNode
                    key={node.id}
                    agent={node}
                    current={node.id === agent.id}
                    onOpen={onOpen}
                  />
                ))}
                {layer.extra > 0 ? (
                  <span className="rd-onode rd-onode-more">另 {layer.extra}</span>
                ) : null}
              </div>
            </div>
          </Fragment>
        ))}
      </div>
      {layers.length < 2 ? (
        <p className="mt-2 text-[10px] text-[var(--console-sub)]">
          {missing > 0 ? '下級不在此名冊' : reportsHere > 0 ? '直屬已列於上方' : '無上級，亦無直屬下級'}
        </p>
      ) : null}
      {missing > 0 ? <p className="mt-2 text-[10px] text-[var(--console-sub)]">另 {missing} 位下級不在此名冊</p> : null}
      {layers.length < 2 && canDelegate.length > 0 ? (
        <p className="mt-2 text-[10px] text-[var(--console-sub)]">
          可委派 {canDelegate.slice(0, 4).map(roleLabel).join('、')}
          {canDelegate.length > 4 ? ` 等 ${canDelegate.length}` : ''}
        </p>
      ) : null}
    </div>
  );
}
