// ==================== Docker 容器管理 ====================

/** 单个容器信息 */
export interface DockerContainer {
  name: string;
  status: string;
  image: string;
  ports: string[];
  health: string;
  uptime: string;
  uptime_seconds: number;
  service: string;
}

/** 容器资源统计 */
export interface DockerContainerStats {
  cpu_percent: number;
  memory_usage: number;
  memory_limit: number;
  network_rx: number;
  network_tx: number;
  error?: string;
}

/** 单个服务健康信息 */
export interface DockerServiceHealth {
  healthy: boolean;
  status: string;
  health_detail: string;
}

/** 健康检查结果 */
export interface DockerHealth {
  all_healthy: boolean;
  services: Record<string, DockerServiceHealth>;
  _error?: string;
}

/** GET /docker/status 回傳 */
export interface DockerStatus {
  available: boolean;
  containers: DockerContainer[];
  health: DockerHealth;
  hourly_rates: Record<string, number>;
}

/** Docker 操作结果 */
export interface DockerActionResult {
  success: boolean;
  service: string;
  message: string;
}

/** Docker 预算状态（公司全权控制） */
export interface DockerBudgetService {
  service: string;
  rate_per_hour: number;
  uptime_hours: number;
  cost: number;
  status: 'running' | 'stopped';
}

export interface CompanyBudgetState {
  api_cost?: number;
  docker_cost: number;
  aliyun_cost?: number;
  cloud_cost?: number;
  total_spent: number;
  budget_pressure: number;
  optimization_suggestions: Array<{
    service: string;
    action: string;
    reason: string;
    estimated_saving_per_hour: number;
    priority: string;
  }>;
  auto_optimized: {
    stopped: string[];
    failed: string[];
    saved_per_hour: number;
  };
  last_updated: string;
}

/** GET /docker/budget 回传 */
export interface DockerBudget {
  available: boolean;
  services: DockerBudgetService[];
  total_docker_cost: number;
  total_hourly_rate: number;
  monthly_projection: number;
  company_budget: CompanyBudgetState;
}
