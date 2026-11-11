/** OPC 監控（GET /monitor/opc）型別。 */

import type { AuditRecord } from '../dashboard';
import type { TaskProgress } from '../task';

export interface OpcTagCatalog {
  name: string;
  unit: string;
  desc: string;
  range: number[];
  writable: boolean;
}

export interface OpcLiveReading {
  tag_name: string;
  value: unknown;
  data_type?: string;
  quality?: string;
  source_timestamp?: string | null;
}

export interface OpcMonitorData {
  guard: {
    write_whitelist: string[];
    write_bounds: Record<string, { min: number; max: number }>;
    require_approval: boolean;
    sim_enabled: boolean;
    opc_server: string;
  };
  catalog: OpcTagCatalog[];
  audit: { recent: AuditRecord[]; summary: Record<string, number> };
    live: {
    reachable: boolean;
    health: { status?: string; opc_connected?: boolean; opc_server?: string } | null;
    browse_tags: Array<Record<string, unknown>>;
    readings: OpcLiveReading[];
    simulated?: boolean;
    error: string | null;
  };
  recent_tasks: TaskProgress[];
  service_url: string;
}
