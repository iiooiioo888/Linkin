/** 帳務相關型別（/billing 帳務 API 契約）。 */

/** 帳務帳戶（/billing API；前端不展示金額） */
export interface BillingAccount {
  user_id: string;
  balance_credits: number;
  pool_balances?: Record<string, number>;
  plan_id: string;
  plan_name_zh: string;
  byok: boolean;
  monthly_quota_credits: number;
  monthly_used_credits: number;
  monthly_remaining_credits: number;
  period_key: string;
  concurrency_limit: number;
  low_balance: boolean;
  features: string[];
  transfer_allowed?: boolean;
  pricing_config_version?: number;
  credit_policy_version?: number;
}

export interface BillingLedgerEntry {
  id: string;
  amount_credits: number;
  balance_after_credits: number;
  kind: 'credit' | 'debit';
  source: string;
  reference: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface PoolLedgerEntry {
  id: string;
  amount_credits: number;
  balance_after_credits: number;
  kind: 'credit' | 'debit';
  source: string;
  reference: string;
  pool_type?: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface BillingUsageEvent {
  id: string;
  event_type: string;
  credits: number;
  quantity: number;
  unit: string;
  task_id: string;
  reference: string;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface BillingDockerPlanTerms {
  plan_id: string;
  plan_name_zh: string;
  rate_multiplier: number;
  included_hours_per_month: number;
  included_hours_used: number;
  included_hours_remaining: number;
  description_zh: string;
  base_hourly_rates_usd?: Record<string, number>;
}

export interface BillingDockerSummary {
  user_id: string;
  plan_id?: string;
  plan_terms?: BillingDockerPlanTerms;
  running_services: Array<{
    service: string;
    owner: string;
    rate_per_hour_usd: number;
    base_rate_per_hour_usd?: number;
    rate_multiplier?: number;
    credits_per_hour: number;
    uptime_hours: number;
    is_core: boolean;
    is_mine?: boolean;
  }>;
  projected_hourly_usd: number;
  projected_hourly_credits: number;
  projected_billable_hourly_usd?: number;
  projected_billable_hourly_credits?: number;
  tick_interval_sec: number;
  recent_docker_events?: BillingUsageEvent[];
  total_docker_credits_spent?: number;
}

export interface BillingPoolsDetail {
  balances: Record<string, number>;
  spendable: number;
  grants: BillingGrant[];
  rollover_records: Record<string, unknown>[];
  rollover_notice_zh: string;
  rollover_policy_version: number;
  cache_stats?: { l3_hits: number; cache_read_tokens: number; savings_credits: number };
}

export interface BillingGrant {
  grant_id: string;
  pool_type: string;
  amount: number;
  remaining: number;
  source: string;
  origin: string;
  lock_days?: number;
  lock_multiplier?: number;
  created_at: string;
}

export interface ContributionStatus {
  unlocked: number;
  locked: number;
  convert_threshold: number;
  accumulated_unlocked: number;
  convertible_to_locked: number;
  convert_ratio_to_purchased: number;
  lock_tiers: Record<string, number>;
  installments?: LockInstallment[];
  threshold_dynamic?: boolean;
  notice_zh?: string;
}

export interface LockInstallment {
  installment_id: string;
  total_amount: number;
  per_installment: number;
  paid_installments: number;
  lock_days: number;
  lock_multiplier: number;
  status: string;
  next_due_at?: string;
  interval_days?: number;
  reward_total?: number;
  reward_paid?: number;
  reward_remaining?: number;
  principal_remaining?: number;
  forfeited_amount?: number;
  failure_reason?: string;
  appeal_deadline?: string;
  schedule_zh?: string;
  progress_zh?: string;
}

export interface BillingAppeal {
  appeal_id: string;
  account_id: string;
  task_id?: string;
  appeal_kind?: string;
  installment_id?: string;
  forfeiture_amount?: number;
  appeal_deadline?: string;
  reason: string;
  detail: string;
  status: string;
  created_at: string;
}

export interface BillingSnapshot {
  account: BillingAccount;
  pools?: BillingPoolsDetail;
  contribution?: ContributionStatus;
  vendor_preference?: { version: number; config: Record<string, unknown> };
  plans: Record<string, unknown>[];
  rate_card: Record<string, unknown>;
  enterprise: Record<string, unknown>;
  docker?: BillingDockerSummary;
}

/** @deprecated 使用 BillingAccount */
export type WalletAccount = BillingAccount & { balance_usd?: number; currency?: string };
export type WalletLedgerEntry = BillingLedgerEntry & { amount_usd?: number; balance_after_usd?: number };
export type WalletSnapshot = BillingSnapshot;
