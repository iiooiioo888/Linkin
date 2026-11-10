// ==================== 雲控制台 ====================

/** 單服務費用明細 */
export interface CloudServiceCost {
  service: string;
  rate: number;
  uptime_hours: number;
  cost: number;
  source?: 'docker' | 'aliyun' | string;
  product_name?: string;
  pretax_amount_cny?: number;
}

/** 阿里雲 BSS 帳目摘要 */
export interface AliyunBilling {
  configured: boolean;
  ok: boolean;
  currency: string;
  cny_usd_rate: number;
  month_total_cny: number;
  month_total_usd: number;
  today_total_cny: number;
  today_total_usd: number;
  products: Array<{
    product_code: string;
    product_name: string;
    pretax_amount_cny: number;
    cost_usd: number;
    source?: string;
  }>;
  error: string | null;
  billing_cycle: string;
}

/** GET /cloud/billing 回傳 */
export interface CloudBilling {
  realtime: Record<string, number>;
  per_service: CloudServiceCost[];
  today_total: number;
  month_total: number;
  month_projected: number;
  total_now: number;
  docker?: {
    realtime: Record<string, number>;
    per_service: CloudServiceCost[];
    total_now: number;
    total_hourly_rate: number;
    month_projected: number;
  };
  aliyun?: AliyunBilling;
  breakdown?: {
    docker_usd: number;
    aliyun_usd: number;
    cloud_total_usd: number;
  };
}

/** 單服務資源數據點 */
export interface CloudServiceMetrics {
  cpu: number;
  mem_mb: number;
  mem_limit_mb: number;
  net_rx_mb: number;
  net_tx_mb: number;
}

/** 監控數據點 */
export interface CloudMonitorPoint {
  ts: string;
  services: Record<string, CloudServiceMetrics>;
}

/** GET /cloud/monitoring 回傳 */
export interface CloudMonitoring {
  points: CloudMonitorPoint[];
  range_hours: number;
  latest: CloudMonitorPoint | null;
}

/** 告警規則 */
export interface CloudAlertRule {
  id: string;
  name: string;
  metric: string;
  threshold: number;
  service: string;
  enabled: boolean;
  created_at: string;
}

/** 告警觸發記錄 */
export interface CloudAlertRecord {
  rule_id: string;
  rule_name: string;
  service: string;
  metric: string;
  value: number;
  threshold: number;
  ts: string;
}

/** GET /cloud/alerts 回傳 */
export interface CloudAlertsData {
  rules: CloudAlertRule[];
  history: CloudAlertRecord[];
}

/** 容器事件 */
export interface CloudEvent {
  ts: string;
  type: string;
  service: string;
  detail: string;
}

/** GET /cloud/events 回傳 */
export interface CloudEventsData {
  events: CloudEvent[];
}
