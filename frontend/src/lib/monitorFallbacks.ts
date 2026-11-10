/**
 * 監控中心前端降級目錄（單一資料源）。
 *
 * 由 `python -m backend.scripts.export_monitor_fallback` 從後端
 * role_catalog / hub.catalog / opc_service 生成，禁止在此手動維護角色清單。
 */
import type { HubMonitorModel, RoleAgent } from '../types';
import { blankMetrics } from './agentUi';
import { markSunsetHubModelsUnavailable } from './sunsetHubIds';
import snapshot from '../generated/monitor-fallback.json';

type MonitorFallbackSnapshot = {
  version: number;
  agents: RoleAgent[];
  hub_models: HubMonitorModel[];
  hub_routing: {
    default_chain: string[];
    cn_chain: string[];
    race_pair: string[];
    forbidden_vendor: string;
  };
};

const data = snapshot as MonitorFallbackSnapshot;

export const AGENT_FALLBACK_ROSTER: RoleAgent[] = data.agents.map((agent) => ({
  ...agent,
  metrics: agent.metrics ?? blankMetrics(),
}));

/** sunset 九鍵標記 available_in_pool=false，移出可選語意；仍保留列供監控降級展示。 */
export const HUB_FALLBACK_MODELS: HubMonitorModel[] = markSunsetHubModelsUnavailable(
  data.hub_models,
);

export const HUB_FALLBACK_ROUTING = data.hub_routing;
