/**
 * Minecraft 模組業務 API（typed wrapper）。
 * 一律走 createModuleClient('minecraft') → /modules/minecraft/api/*。
 */
import { createModuleClient } from './modules';

const mc = createModuleClient('minecraft');

export type Constitution = {
  world_name: string;
  world_name_zh_hant?: string;
  tagline?: string;
  foundation?: Record<string, unknown>;
  factions?: Array<Record<string, unknown>>;
  magic?: Record<string, unknown>;
  regions?: Array<Record<string, unknown>>;
  content_boundaries?: string[];
  consistency_rules?: string[];
  item_balance?: Record<string, unknown>;
};

export type NpcCard = {
  id?: string;
  name: string;
  faction: string;
  occupation: string;
  personality: string;
  backstory: string;
  location: string;
  speech_style: string;
  relationships?: Record<string, string>;
  backend?: string;
};

export type QuestObjective = {
  id: string;
  title: string;
  description?: string;
  done?: boolean;
  updated_at?: number | null;
};

export type Quest = {
  id: string;
  title: string;
  quest_type: string;
  difficulty: string;
  region?: string;
  description?: string;
  objectives?: QuestObjective[];
  world_status?: string;
};

export type QuestProgressRow = {
  id: string;
  player_id: string;
  quest_id: string;
  status: 'active' | 'completed' | 'failed' | string;
  objectives?: Record<string, { done?: boolean; updated_at?: number | null }>;
  objectives_detail?: QuestObjective[];
  objectives_done?: number;
  objectives_total?: number;
  quest_title?: string;
  quest_type?: string;
  quest_region?: string;
  world_status?: string;
  started_at?: number;
  updated_at?: number;
  completed_at?: number | null;
  last_event_id?: string | null;
  notes?: Array<{ ts?: number; text?: string; objective_id?: string; source?: string }>;
};

export type QuestProgressSummary = {
  active: number;
  completed: number;
  failed: number;
  active_quests: QuestProgressRow[];
};

export type Building = {
  id: string;
  prompt: string;
  style: string;
  location: unknown;
  region?: string;
  block_count: number;
  status?: string;
  note?: string;
  kind?: string;
  width?: number;
  height?: number;
  length?: number;
  voxel_count?: number;
  schematic_version?: number;
  format?: string;
  biome?: string;
};

export type BuildingPreview = {
  id: string;
  kind?: string;
  width: number;
  height: number;
  length: number;
  version: number;
  data_version?: number;
  voxel_count: number;
  biome?: string;
  palette: Array<{ name: string; color: string; opacity?: number; emissive?: string }>;
  voxels: Array<{ x: number; y: number; z: number; i: number }>;
  schematic_base64?: string;
  schematic_filename?: string;
  building?: Partial<Building>;
};

export type Item = {
  id: string;
  name: string;
  type: string;
  rarity: string;
  attributes: Record<string, unknown>;
  description?: string;
};

export type WorldEvent = {
  id: string;
  text: string;
  kind?: string;
  title?: string;
  updated_at?: string;
};

export type Overview = {
  world_name: string;
  will?: string;
  npc_count: number;
  quest_count: number;
  event_count: number;
  item_count: number;
  building_count: number;
  player_records?: number;
  factions: string[];
  magic?: string;
  compliance: {
    constitution_loaded: boolean;
    factions_defined: boolean;
    magic_defined: boolean;
    rag: { chroma: boolean; fallback?: string | null; error?: string | null };
    minecraft?: {
      dry_run?: boolean;
      enabled?: boolean;
      connected?: boolean;
    };
  };
  minecraft?: MinecraftStatus;
};

export type MinecraftAudit = {
  ts?: string;
  tool?: string;
  remote?: string;
  ok?: boolean;
  dry_run?: boolean;
  error?: string;
  duration_ms?: number;
};

export type MinecraftPluginProbe = {
  checked_at?: string;
  url?: string;
  ok?: boolean;
  status?: string;
  status_code?: number | null;
  method?: string | null;
  error?: string | null;
  embeddable_hint?: string | null;
};

export type MinecraftPluginCatalogEntry = {
  id: string;
  name: string;
  category: string;
  purpose: string;
  platforms: string[];
  install_hint: string;
  config_fields: Array<{ key: string; label: string; required?: boolean; example?: string }>;
  embeddable: boolean;
  related_flows?: string[];
  enabled?: boolean;
  map_url?: string | null;
  api_port?: number | null;
  active_map?: boolean;
  status?: string;
  last_probe?: MinecraftPluginProbe | null;
};

export type MinecraftPluginSettings = {
  version?: number;
  updated_at?: string;
  active_map_plugin?: string | null;
  map_url?: string | null;
  plugins: Record<
    string,
    {
      enabled?: boolean;
      map_url?: string | null;
      api_port?: number | null;
      last_probe?: MinecraftPluginProbe | null;
    }
  >;
  catalog_count?: number;
};

export type MinecraftPluginsSummary = {
  active_map_plugin?: string | null;
  map_url?: string | null;
  map_plugins?: Record<string, string>;
  configured_count?: number;
  reachable_count?: number;
};

export type MinecraftStatus = {
  enabled: boolean;
  live: boolean;
  dry_run: boolean;
  url: string;
  world: string;
  token_configured: boolean;
  connected?: boolean;
  max_blocks?: number;
  company_tools?: string[];
  tools?: string[];
  recent?: MinecraftAudit[];
  plugins?: MinecraftPluginsSummary;
  probe?: {
    ok?: boolean;
    connected?: boolean;
    dry_run?: boolean;
    message?: string;
    error?: string;
    remote_tools?: string[];
  };
};

export const fetchConstitution = () => mc.get<Constitution>('/constitution');
export const saveConstitution = (body: Record<string, unknown>) =>
  mc.put<Constitution>('/constitution', body);

export const fetchNpcs = () => mc.get<{ npcs: NpcCard[]; count: number }>('/npcs');
export const createNpc = (body: NpcCard) => mc.post<{ npc: NpcCard }>('/npcs', body);
export const updateNpc = (id: string, body: Partial<NpcCard>) =>
  mc.put<{ npc: NpcCard }>(`/npcs/${id}`, body);
export const deleteNpc = (id: string) => mc.del<{ deleted: boolean }>(`/npcs/${id}`);
export const npcDialogue = (id: string, playerMessage: string) =>
  mc.post<{ reply: string; rag: { hits: unknown[]; backend: unknown } }>(`/npcs/${id}/dialogue`, {
    playerMessage,
  });

export const generateQuest = (body: { playerId: string; questType: string; difficulty: string; region?: string }) =>
  mc.post<{ quest: Quest }>('/quests/generate', body);
export const fetchQuests = () => mc.get<{ quests: Quest[]; count: number }>('/quests');
export const deleteQuest = (id: string) => mc.del<{ deleted: boolean }>(`/quests/${id}`);

export const generateBuilding = (body: {
  prompt: string;
  style: string;
  location: string;
  region: string;
  block_count: number;
}) => mc.post<{ building: Building; preview?: BuildingPreview | null }>('/buildings/generate', body);
export const fetchBuildings = () => mc.get<{ buildings: Building[]; count: number }>('/buildings');
export const fetchBuildingPreview = (id: string) => mc.get<BuildingPreview>(`/buildings/${id}/preview`);
export const schematicUrl = (id: string) => mc.url(`/buildings/${id}/schematic`);
export const deleteBuilding = (id: string) => mc.del<{ deleted: boolean }>(`/buildings/${id}`);

export const importSchematicBase64 = (
  schematicBase64: string,
  meta: { prompt?: string; style?: string; location?: string; region?: string },
) =>
  mc.post<{ building: Building; preview: BuildingPreview }>('/buildings/import-base64', {
    schematic_base64: schematicBase64,
    prompt: meta.prompt ?? '',
    style: meta.style ?? '',
    location: meta.location ?? '',
    region: meta.region ?? '',
  });

export async function importSchematic(
  file: File,
  meta: { prompt?: string; style?: string; location?: string; region?: string },
): Promise<{ building: Building; preview: BuildingPreview }> {
  const form = new FormData();
  form.append('file', file);
  if (meta.prompt) form.append('prompt', meta.prompt);
  if (meta.style) form.append('style', meta.style);
  if (meta.location) form.append('location', meta.location);
  if (meta.region) form.append('region', meta.region);
  return mc.form<{ building: Building; preview: BuildingPreview }>('/buildings/import', form);
}

export const fetchItems = () => mc.get<{ items: Item[]; count: number }>('/items');
export const createItem = (body: Omit<Item, 'id'>) => mc.post<{ item: Item }>('/items', body);
export const deleteItem = (id: string) => mc.del<{ deleted: boolean }>(`/items/${id}`);

export const fetchEvents = () => mc.get<{ events: WorldEvent[]; count: number }>('/events');

export const fetchOverview = () => mc.get<Overview>('/overview');

export const fetchMinecraftStatus = () => mc.get<MinecraftStatus>('/minecraft/status');
export const probeMinecraft = () => mc.post<MinecraftStatus['probe']>('/minecraft/probe');
export const callMinecraftTool = (tool: string, arguments_: Record<string, unknown>) =>
  mc.post<Record<string, unknown>>('/minecraft/call', { tool, arguments: arguments_ });

export const fetchMinecraftPluginCatalog = () =>
  mc.get<{ plugins: MinecraftPluginCatalogEntry[]; count: number }>('/minecraft/plugins/catalog');
export const fetchMinecraftPluginSettings = () => mc.get<MinecraftPluginSettings>('/minecraft/plugins/settings');
export const saveMinecraftPluginSettings = (body: {
  active_map_plugin?: string | null;
  plugins?: Record<string, { enabled?: boolean; map_url?: string; api_port?: number | null }>;
}) => mc.put<MinecraftPluginSettings>('/minecraft/plugins/settings', body);
export const probeMinecraftPlugin = (pluginId: string) =>
  mc.post<{
    plugin_id: string;
    map_url: string;
    probe: MinecraftPluginProbe;
    embeddable: boolean;
    connection_status: string;
  }>(`/minecraft/plugins/${pluginId}/probe`);
export const dispatchBuilding = (id: string) =>
  mc.post<{ building: Building; minecraft: Record<string, unknown> }>(`/buildings/${id}/dispatch`);

export const executeAdminCommand = (command: string, confirmed = false) =>
  mc.post<{ executed: boolean; command: string; sensitive?: boolean; minecraft?: Record<string, unknown> }>(
    '/admin/execute',
    { command, confirmed },
  );

export type ServerHealthCheck = {
  name: string;
  ok: boolean;
  warning?: boolean;
  critical?: boolean;
  detail?: string;
};

export type ServerHealth = {
  status: string;
  dry_run?: boolean;
  storage_root?: string;
  checks: ServerHealthCheck[];
  ts?: number;
  error?: string;
};

export type ServerApproval = {
  id: string;
  tool: string;
  params?: Record<string, unknown>;
  question?: string;
  preview?: Record<string, unknown>;
  status: string;
  created_ts?: number;
  ttl_min?: number;
};

export type ServerAuditEntry = {
  ts?: string;
  tool?: string;
  ok?: boolean;
  message?: string;
  error?: string;
  [key: string]: unknown;
};

export const fetchServerHealth = () => mc.get<ServerHealth>('/server/health');
export const askServerAdmin = (question: string) =>
  mc.post<Record<string, unknown>>('/server/ask', { question });
export const fetchServerApprovals = (includeDone = false) =>
  mc.get<{ approvals: ServerApproval[]; count: number }>(
    `/server/approvals${includeDone ? '?include_done=true' : ''}`,
  );
export const confirmServerApproval = (id: string) =>
  mc.post<Record<string, unknown>>(`/server/approvals/${encodeURIComponent(id)}/confirm`);
export const cancelServerApproval = (id: string) =>
  mc.post<Record<string, unknown>>(`/server/approvals/${encodeURIComponent(id)}/cancel`);
export const runServerPatrol = () => mc.post<Record<string, unknown>>('/server/patrol');
export const fetchServerReport = () => mc.get<{ report: string }>('/server/report');
export const fetchServerAudit = (limit = 40) =>
  mc.get<{ entries: ServerAuditEntry[]; count: number }>(`/server/audit?limit=${limit}`);

export type NarrativeWorkspaceState = 'active' | 'awaiting_confirmation' | 'committed' | 'discarded';

export type NarrativeWorkspace = {
  workspace_id: string;
  task_id: string;
  snapshot_id: string;
  state: NarrativeWorkspaceState;
  draft_keys: string[];
  drafts?: Record<string, unknown>;
  created_at?: number;
};

export type NarrativeCommitResult = {
  ok: boolean;
  workspace: NarrativeWorkspace;
  committed: Record<string, { id?: string; title?: string; kind?: string; [key: string]: unknown }>;
  errors: Array<{ key: string; code: string; message: string }>;
};

export const beginNarrativeWorkspace = (body: { task_id: string; snapshot_id: string }) =>
  mc.post<{ ok: boolean; workspace: NarrativeWorkspace; known_draft_keys: string[] }>(
    '/narrative/workspaces',
    body,
  );

export const listNarrativeWorkspaces = (taskId?: string) =>
  mc.get<{ workspaces: NarrativeWorkspace[]; count: number }>(
    `/narrative/workspaces${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ''}`,
  );

export const fetchNarrativeWorkspace = (workspaceId: string) =>
  mc.get<{ ok: boolean; workspace: NarrativeWorkspace; known_draft_keys: string[] }>(
    `/narrative/workspaces/${encodeURIComponent(workspaceId)}`,
  );

export const writeNarrativeDraft = (workspaceId: string, key: string, value: unknown) =>
  mc.put<{ ok: boolean; workspace: NarrativeWorkspace }>(
    `/narrative/workspaces/${encodeURIComponent(workspaceId)}/drafts/${encodeURIComponent(key)}`,
    { value },
  );

export const commitNarrativeWorkspace = (workspaceId: string) =>
  mc.post<NarrativeCommitResult>(`/narrative/workspaces/${encodeURIComponent(workspaceId)}/commit`);

export const confirmNarrativeWorkspace = (
  workspaceId: string,
  body: { choice: 'rebind' | 'discard'; new_snapshot_id?: string },
) =>
  mc.post<{ ok: boolean; workspace: NarrativeWorkspace }>(
    `/narrative/workspaces/${encodeURIComponent(workspaceId)}/confirm`,
    body,
  );

export const refreshNarrativeL0 = (newSnapshotId: string) =>
  mc.post<{ ok: boolean; affected_workspace_ids: string[]; count: number }>(
    '/narrative/workspaces/refresh-l0',
    { new_snapshot_id: newSnapshotId },
  );

export const seedNarrativeStarterPack = (
  workspaceId: string,
  body?: { region?: string; theme?: string },
) =>
  mc.post<{ ok: boolean; source: 'fallback' | 'llm'; workspace: NarrativeWorkspace; draft_keys: string[] }>(
    `/narrative/workspaces/${encodeURIComponent(workspaceId)}/starter-pack`,
    body ?? {},
  );

export type MapPlanPlot = {
  id: string;
  kind: 'marker' | 'poi' | 'path' | 'terrain';
  title: string;
  location?: { x: number; y: number; z: number };
  material?: string;
  style?: string;
  link?: Record<string, unknown>;
  points?: Array<{ x: number; y: number; z: number }>;
  width?: number;
  geometry?: Record<string, unknown>;
};

export type MapPlan = {
  version: number;
  id: string;
  title: string;
  region: string;
  seed: string;
  origin: { x: number; y: number; z: number };
  bounds: { x1: number; y1: number; z1: number; x2: number; y2: number; z2: number };
  plots: MapPlanPlot[];
  landmarks?: Array<{ id: string; title: string; location: { x: number; y: number; z: number }; notes?: string }>;
  summary?: string;
  source?: string;
  estimated_blocks?: number;
  status?: string;
};

export type MapPlanPreview = {
  plan_id: string;
  title: string;
  region: string;
  bounds: MapPlan['bounds'];
  axis_span: { x: number; y: number; z: number };
  plot_count: number;
  estimated_blocks: number;
  pois: Array<{
    id: string;
    title: string;
    kind: string;
    location: string;
    material?: string;
    link?: Record<string, unknown>;
    notes?: string;
  }>;
  paths: string[];
  terrain_patches: string[];
};

export const generateMapPlan = (body: {
  workspace_id?: string;
  region?: string;
  seed?: string;
  origin?: string | { x: number; y: number; z: number };
}) =>
  mc.post<{ ok: boolean; source: 'fallback' | 'llm'; plan: MapPlan; preview: MapPlanPreview }>(
    '/map/generate',
    body,
  );

export const previewMapPlan = (body: { plan?: MapPlan; plan_id?: string }) =>
  mc.post<{ ok: boolean; preview: MapPlanPreview }>('/map/preview', body);

export const applyMapPlan = (body: { plan?: MapPlan; plan_id?: string; confirm?: boolean }) =>
  mc.post<{
    ok: boolean;
    status: 'complete' | 'partial' | 'failed';
    plan: MapPlan;
    minecraft: {
      ok: boolean;
      dry_run?: boolean;
      applied?: Array<Record<string, unknown>>;
      errors?: Array<Record<string, unknown>>;
      blocks_placed?: number;
      note?: string;
    };
  }>('/map/apply', body);

export type NarrativeGenerateResult = {
  ok: boolean;
  source: 'llm';
  replaced_keys: string[];
  workspace: NarrativeWorkspace;
  draft_keys: string[];
};

export const generateNarrativeDrafts = (
  workspaceId: string,
  body: {
    brief: string;
    locale?: string;
    keys?: string[];
    region?: string;
    theme?: string;
  },
) =>
  mc.post<NarrativeGenerateResult>(
    `/narrative/workspaces/${encodeURIComponent(workspaceId)}/generate`,
    body,
  );

export type PipelineStepStatus = 'pending' | 'running' | 'ok' | 'error' | 'partial' | 'skipped';

export type PipelineStep = {
  id: string;
  label: string;
  status: PipelineStepStatus;
  message?: string;
  detail?: Record<string, unknown>;
};

export type NarrativePipelineResult = {
  ok: boolean;
  status: PipelineStepStatus;
  confirm_world: boolean;
  needs_confirm: boolean;
  bridge: MinecraftStatus;
  workspace_id?: string;
  workspace?: NarrativeWorkspace;
  committed?: Record<string, { id?: string; title?: string; [key: string]: unknown }>;
  commit_errors?: Array<{ key: string; code: string; message: string }>;
  build_brief_id?: string | null;
  map_plan?: MapPlan | null;
  map_preview?: MapPlanPreview | null;
  steps: PipelineStep[];
  plan?: {
    confirm_world_required?: boolean;
    build_brief_id?: string | null;
    map_plan_id?: string;
    pending_world_count?: number;
    message?: string;
  };
  elapsed_ms?: number;
  message?: string;
};

export const runNarrativePipeline = (body: {
  brief?: string;
  workspace_id?: string;
  task_id?: string;
  snapshot_id?: string;
  region?: string;
  theme?: string;
  seed?: string;
  confirm_world?: boolean;
  regenerate?: boolean;
  use_starter_pack?: boolean;
  options?: { steps?: Record<string, boolean> };
}) => mc.post<NarrativePipelineResult>('/narrative/pipelines/run', body);

export const fetchNarrativePipelineSteps = () =>
  mc.get<{ steps: Array<{ id: string; label: string }> }>('/narrative/pipelines/steps');

export type BuildBrief = {
  id: string;
  title: string;
  region: string;
  location: string;
  style: string;
  prompt: string;
  block_count: number;
  notes?: string;
  status?: string;
  source?: string;
  building_id?: string;
  build_job?: {
    blocks_total?: number;
    blocks_placed?: number;
    blocks_failed?: number;
    dry_run?: boolean;
    cancelled?: boolean;
  };
};

export type BuildBriefPreview = {
  brief: BuildBrief;
  building?: Building | null;
  bounds: {
    anchor?: { x: number; y: number; z: number };
    world_min?: { x: number; y: number; z: number };
    world_max?: { x: number; y: number; z: number };
    solid_count: number;
    width?: number;
    height?: number;
    length?: number;
    estimate_only?: boolean;
  };
  preview?: BuildingPreview | null;
  bridge: { enabled?: boolean; connected?: boolean; dry_run?: boolean };
  dry_run: boolean;
};

export type BuildBriefApplyResult = {
  brief: BuildBrief;
  building: Building;
  placement: {
    ok: boolean;
    dry_run?: boolean;
    cancelled?: boolean;
    blocks_total: number;
    blocks_placed: number;
    blocks_failed: number;
    bounds?: BuildBriefPreview['bounds'];
    errors?: string[];
    note?: string;
  };
  bridge?: MinecraftStatus;
  dry_run?: boolean;
};

export type BuildBriefJob = {
  job_id: string;
  brief_id: string;
  status: string;
  dry_run: boolean;
  blocks_total: number;
  blocks_placed: number;
  blocks_failed: number;
  error?: string | null;
  cancel_requested?: boolean;
  result?: BuildBriefApplyResult | null;
};

export const fetchBuildBriefs = () =>
  mc.get<{ build_briefs: BuildBrief[]; count: number }>('/build-briefs');

export const fetchBuildBrief = (id: string) =>
  mc.get<{ build_brief: BuildBrief }>(`/build-briefs/${encodeURIComponent(id)}`);

export const previewBuildBrief = (briefId: string) =>
  mc.post<BuildBriefPreview>(`/build-briefs/${encodeURIComponent(briefId)}/preview`, {});

export const applyBuildBrief = (briefId: string) =>
  mc.post<BuildBriefApplyResult>('/build-briefs/apply', { brief_id: briefId, confirm: true });

export const applyBuildBriefAsync = (briefId: string) =>
  mc.post<{ job: BuildBriefJob }>('/build-briefs/apply', {
    brief_id: briefId,
    confirm: true,
    async: true,
  });

export const fetchBuildBriefJob = (jobId: string) =>
  mc.get<{ job: BuildBriefJob }>(`/build-briefs/jobs/${encodeURIComponent(jobId)}`);

export const cancelBuildBriefJob = (jobId: string) =>
  mc.post<{ job: BuildBriefJob }>(`/build-briefs/jobs/${encodeURIComponent(jobId)}/cancel`);

export type WorldIntentEntity = {
  id: string;
  kind: 'npc' | 'quest' | 'item';
  title?: string;
  name?: string;
  world_status?: string;
  region?: string;
  location?: string;
  source?: string;
};

export type PendingWorldIntents = {
  npcs: WorldIntentEntity[];
  quests: WorldIntentEntity[];
  items: WorldIntentEntity[];
  count: number;
};

export type WorldIntentPreview = {
  kind: 'npc' | 'quest' | 'item';
  id: string;
  title: string;
  spawn?: { x: number; y: number; z: number };
  actions?: Array<{ tool: string; description: string; material?: string; command?: string }>;
  store?: string;
  world_status?: string;
};

export type WorldIntentApplyRow = {
  kind: 'npc' | 'quest' | 'item';
  id: string;
  title?: string;
  world_status?: string;
  skipped?: boolean;
  store?: { ok: boolean; note?: string; entity?: Record<string, unknown> };
  minecraft?: { ok: boolean; skipped?: boolean };
  next_steps?: string[];
};

export type WorldIntentApplyResult = {
  results: WorldIntentApplyRow[];
  summary: {
    overall_status: 'applied' | 'partial' | 'failed' | 'skipped';
    applied: number;
    partial: number;
    skipped: number;
    failed: number;
    total: number;
  };
  bridge?: MinecraftStatus & {
    spawn_mode?: string;
    bridge_offline?: boolean;
    note?: string;
  };
  dry_run?: boolean;
};

export const fetchPendingWorldIntents = () =>
  mc.get<{ pending: PendingWorldIntents; count: number }>('/world-intents');

export const previewWorldIntents = (body: { apply_all?: boolean; npc_ids?: string[]; quest_ids?: string[]; item_ids?: string[] }) =>
  mc.post<{ intents: WorldIntentPreview[]; count: number; bridge: MinecraftStatus; dry_run: boolean }>(
    '/world-intents/preview',
    body,
  );

export const applyWorldIntents = (body: { apply_all?: boolean; npc_ids?: string[]; quest_ids?: string[]; item_ids?: string[] }) =>
  mc.post<WorldIntentApplyResult>('/world-intents/apply', { ...body, confirm: true });

export type MinecraftObservabilityEvent = {
  id: string;
  ts: number;
  domain: string;
  action: string;
  status: string;
  summary: string;
  dry_run?: boolean;
  bridge_offline?: boolean;
  details?: Record<string, unknown>;
  entity_refs?: Record<string, unknown>;
};

export type MinecraftBridgeSetup = {
  enabled?: boolean;
  url_set?: boolean;
  token_set?: boolean;
  world_set?: boolean;
  all_ready?: boolean;
  connected?: boolean;
  dry_run?: boolean;
  probe_ok?: boolean | null;
  probe_message?: string;
};

export type MinecraftMonitorSummary = {
  bridge: {
    enabled?: boolean;
    connected?: boolean;
    dry_run?: boolean;
    live?: boolean;
    token_configured?: boolean;
    world?: string;
    url?: string;
  };
  bridge_setup?: MinecraftBridgeSetup;
  plugins?: MinecraftPluginsSummary;
  kpis: {
    pending_build_briefs: number;
    pending_world_intents: number;
    map_plan_count: number;
    npc_count: number;
    quest_count: number;
    item_count: number;
    active_quest_progress?: number;
    online_players?: number;
    players_live?: {
      online_count: number;
      bridge_offline?: boolean;
      recent_events?: number;
    };
  };
  players?: MinecraftPlayersAiBlock;
  world_status: Record<string, Record<string, number>>;
  last_pipeline: MinecraftObservabilityEvent | null;
  pipeline_timeline?: MinecraftObservabilityEvent[];
  recent_errors: MinecraftObservabilityEvent[];
  bridge_errors?: MinecraftObservabilityEvent[];
  generated_at: number;
};

export type LayoutPreviewFeature = {
  id: string;
  type: 'point' | 'rect' | 'polyline';
  kind: string;
  title: string;
  status: string;
  label: string;
  source: string;
  color: string;
  point?: { x: number; z: number };
  rect?: { x1: number; z1: number; x2: number; z2: number };
  polyline?: { points: Array<{ x: number; z: number }>; width: number };
  meta?: Record<string, unknown>;
};

export type LayoutPreviewPlayer = {
  id: string;
  name: string;
  x: number;
  y?: number | null;
  z: number;
  dimension?: string | null;
  health?: number | null;
  gamemode?: string | null;
  held_summary?: { name: string; count: number } | null;
  inventory_summary?: Array<{ name: string; count: number }>;
};

export type LayoutPreviewPlayersLive = {
  online_count: number;
  bridge_offline?: boolean;
  waiting?: boolean;
  hint?: string | null;
};

export type LayoutPreviewData = {
  ok: boolean;
  empty: boolean;
  mode: string;
  note: string;
  has_map_plan: boolean;
  map_plan: {
    id: string;
    title: string;
    region: string;
    status?: string;
    source?: string;
    estimated_blocks?: number;
  } | null;
  region: string | null;
  bounds: { x1: number; z1: number; x2: number; z2: number };
  view: { width: number; depth: number; center: { x: number; z: number } };
  legend: Array<{ kind: string; label: string; color: string }>;
  features: LayoutPreviewFeature[];
  counts: {
    plots: number;
    build_briefs: number;
    npc_intents: number;
    landmarks: number;
    total: number;
  };
  layout_summary?: {
    feature_count: number;
    bounds: { x1: number; z1: number; x2: number; z2: number };
    has_map_plan: boolean;
    region: string | null;
    online_players?: number;
  };
  players?: LayoutPreviewPlayer[];
  players_live?: LayoutPreviewPlayersLive;
  generated_at: number;
};

export type MinecraftSituationDimension = {
  status: 'ok' | 'partial' | 'unknown';
  signals: Array<{ name: string; value: unknown; unit?: string; note?: string }>;
  summary: string;
  confidence: number;
};

export type MinecraftSituationRuleRecommendation = {
  id: string;
  action_type: string;
  message: string;
  rationale?: string;
  priority?: number;
  auto_apply_safe?: boolean;
  payload?: Record<string, unknown>;
};

export type MinecraftSituationSnapshot = {
  generated_at: number;
  market: MinecraftSituationDimension;
  economy: MinecraftSituationDimension;
  land: MinecraftSituationDimension;
  players: MinecraftSituationDimension;
  hints: string[];
  rule_recommendations?: MinecraftSituationRuleRecommendation[];
  region_focus?: Record<string, unknown>;
};

export type MinecraftAiSnapshot = MinecraftMonitorSummary & {
  pending_intents: PendingWorldIntents & { count: number };
  latest_map_plan: MapPlan | null;
  layout_summary?: LayoutPreviewData['layout_summary'];
  active_workspaces: Array<{ workspace_id: string; state: string; draft_keys: string[] }>;
  recent_events: MinecraftObservabilityEvent[];
  situation?: MinecraftSituationSnapshot;
};

export type MinecraftAiContext = {
  format: 'markdown' | 'json';
  context: string;
  chars: number;
  truncated: boolean;
  snapshot: MinecraftAiSnapshot;
};

export type MinecraftPlayerSummary = {
  id: string;
  name: string;
  uuid?: string | null;
  dimension?: string | null;
  world?: string | null;
  position?: { x: number; y: number; z: number } | null;
  health?: number | null;
  food?: number | null;
  gamemode?: string | null;
  last_seen?: number;
  inventory_summary?: Array<{ name: string; count: number }>;
};

export type MinecraftPlayersSnapshot = {
  bridge: {
    enabled?: boolean;
    connected?: boolean;
    dry_run?: boolean;
    live?: boolean;
  };
  bridge_offline: boolean;
  online_count: number;
  players: MinecraftPlayerSummary[];
  generated_at: number;
};

export type MinecraftPlayerDetail = MinecraftPlayerSummary & {
  online?: boolean;
  inventory?: {
    slots?: Array<{ slot?: number | string; name: string; count: number }>;
    armor?: Array<{ slot?: number | string; name: string; count: number }>;
    held?: { name: string; count: number } | null;
  };
  held?: { name: string; count: number } | null;
  armor?: Array<{ slot?: number | string; name: string; count: number }>;
  slots?: Array<{ slot?: number | string; name: string; count: number }>;
};

export type MinecraftPlayersAiBlock = {
  bridge_offline?: boolean;
  online_count?: number;
  players?: MinecraftPlayerSummary[];
  recent_activity?: MinecraftObservabilityEvent[];
  activity_lines?: string[];
};

export const fetchMinecraftMonitorSummary = () =>
  mc.get<MinecraftMonitorSummary>('/minecraft/monitor/summary');

export const fetchMinecraftSituation = () =>
  mc.get<MinecraftSituationSnapshot>('/minecraft/situation');

export const fetchMinecraftSituationDimension = (dimension: string) =>
  mc.get<MinecraftSituationDimension & { generated_at: number; dimension: string }>(
    `/minecraft/situation/${encodeURIComponent(dimension)}`,
  );

export const fetchMinecraftAiSnapshot = () => mc.get<MinecraftAiSnapshot>('/minecraft/ai/snapshot');

export const fetchMinecraftAiEvents = (params?: { since?: number; cursor?: string; limit?: number }) => {
  const qs = new URLSearchParams();
  if (params?.since != null) qs.set('since', String(params.since));
  if (params?.cursor) qs.set('cursor', params.cursor);
  if (params?.limit != null) qs.set('limit', String(params.limit));
  const suffix = qs.toString() ? `?${qs}` : '';
  return mc.get<{
    events: MinecraftObservabilityEvent[];
    count: number;
    total: number;
    next_cursor: string | null;
    has_more: boolean;
  }>(`/minecraft/ai/events${suffix}`);
};

export const fetchMinecraftAiContext = (maxChars = 8000, format: 'markdown' | 'json' = 'markdown') =>
  mc.get<MinecraftAiContext>(`/minecraft/ai/context?max_chars=${maxChars}&format=${format}`);

export const fetchMinecraftLayoutPreview = (params?: { plan_id?: string; region?: string }) => {
  const qs = new URLSearchParams();
  if (params?.plan_id) qs.set('plan_id', params.plan_id);
  if (params?.region) qs.set('region', params.region);
  const suffix = qs.toString() ? `?${qs}` : '';
  return mc.get<LayoutPreviewData>(`/minecraft/layout-preview${suffix}`);
};

export const fetchMinecraftPlayers = (sync = true) =>
  mc.get<MinecraftPlayersSnapshot>(`/minecraft/players?sync=${sync ? 'true' : 'false'}`);

export const fetchMinecraftPlayerDetail = (playerId: string, sync = false) =>
  mc.get<{ ok: boolean; error?: string; bridge_offline?: boolean; player: MinecraftPlayerDetail | null }>(
    `/minecraft/players/${encodeURIComponent(playerId)}?sync=${sync ? 'true' : 'false'}`,
  );

export const fetchMinecraftPlayerEvents = (params?: {
  since?: number;
  cursor?: string;
  limit?: number;
  player_id?: string;
  action?: string;
}) => {
  const qs = new URLSearchParams();
  if (params?.since != null) qs.set('since', String(params.since));
  if (params?.cursor) qs.set('cursor', params.cursor);
  if (params?.limit != null) qs.set('limit', String(params.limit));
  if (params?.player_id) qs.set('player_id', params.player_id);
  if (params?.action) qs.set('action', params.action);
  const suffix = qs.toString() ? `?${qs}` : '';
  return mc.get<{
    events: MinecraftObservabilityEvent[];
    count: number;
    total?: number;
    next_cursor: string | null;
    has_more?: boolean;
  }>(`/minecraft/players/events${suffix}`);
};

export const ingestMinecraftPlayerEvent = (body: Record<string, unknown>) =>
  mc.post<{ ok: boolean; event?: MinecraftObservabilityEvent; error?: string }>('/minecraft/players/ingest', body);

export type MinecraftGmConfig = {
  enabled: boolean;
  auto_apply: boolean;
  dry_run: boolean;
  max_actions_per_event: number;
  cooldown_seconds: number;
};

export type MinecraftGmRun = {
  id: string;
  ts: number;
  trigger_event_id?: string;
  player_id?: string;
  player_name?: string;
  trigger_action?: string;
  rationale?: string;
  actions?: Array<Record<string, unknown>>;
  apply_results?: Array<Record<string, unknown>>;
  dry_run?: boolean;
  auto_apply?: boolean;
  applied?: boolean;
  status?: string;
  source?: string;
};

export const fetchMinecraftGmConfig = () =>
  mc.get<{ config: MinecraftGmConfig }>('/minecraft/gm/config');

export const updateMinecraftGmConfig = (patch: Partial<MinecraftGmConfig>) =>
  mc.put<{ config: MinecraftGmConfig }>('/minecraft/gm/config', patch);

export const fetchMinecraftGmRuns = (limit = 30) =>
  mc.get<{ runs: MinecraftGmRun[]; count: number }>(`/minecraft/gm/runs?limit=${limit}`);

export const tickMinecraftGm = (limit = 5) =>
  mc.post<{ ok: boolean; processed?: number; results?: unknown[]; error?: string }>(
    `/minecraft/gm/tick?limit=${limit}`,
    {},
  );

export const reactMinecraftGm = (eventId: string, force = false) =>
  mc.post<{ ok: boolean; run?: MinecraftGmRun; error?: string }>('/minecraft/gm/react', {
    event_id: eventId,
    force,
  });

export const fetchQuestProgress = (params?: { player_id?: string; quest_id?: string; status?: string }) => {
  const qs = new URLSearchParams();
  if (params?.player_id) qs.set('player_id', params.player_id);
  if (params?.quest_id) qs.set('quest_id', params.quest_id);
  if (params?.status) qs.set('status', params.status);
  const suffix = qs.toString() ? `?${qs}` : '';
  return mc.get<{ progress: QuestProgressRow[]; count: number }>(`/minecraft/quests/progress${suffix}`);
};

export const fetchQuestProgressSummary = (limit = 12) =>
  mc.get<QuestProgressSummary>(`/minecraft/quests/progress/summary?limit=${limit}`);

export const applyQuestProgress = (body: {
  player_id: string;
  quest_id: string;
  objective_id?: string;
  status?: 'advance' | 'complete' | 'failed';
  note?: string;
  dry_run?: boolean;
}) => mc.post<Record<string, unknown>>('/minecraft/quests/progress/apply', body);
