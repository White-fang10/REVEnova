export type Summary = {
  currency: string;
  revenue_at_risk: number;
  predicted_recovery: number;
  actual_recovery: number;
  recovery_rate: number;
  active_cases: number;
  active_revenue_at_risk: number;
  predicted_recovery_active: number;
  case_counts: {
    total: number;
    open: number;
    recovered: number;
    escalated: number;
    closed: number;
    stopped: number;
  };
  learned_strategy_count: number;
};

export type LeakBucket = {
  type: string;
  revenue_at_risk: number;
  cases: number;
  predicted_recovery: number;
};

export type DetectedLeak = {
  dimension: string;
  value: string;
  current_rate: number;
  baseline_rate: number;
  zscore: number;
  delta_pts: number;
  affected_count: number;
  revenue_at_risk: number;
  rate_multiplier: number;
};

export type Strategy = {
  key: string;
  name: string;
  predicted_recovery: number;
  expected_value: number;
  intervention_cost: number;
  friction_cost: number;
  cost_tier: string;
  revenue_at_risk: number;
  message?: string | null;
  AI_proposed: boolean;
  recommended?: boolean;
  id?: number;
};

export type AgentTrace = {
  tool: string;
  note?: string;
  at: string;
};

export type CaseDetail = {
  id: number;
  case_code: string;
  status: string;
  revenue_at_risk: number;
  recovery_probability: number;
  root_cause: string;
  confidence: number;
  leak_type: string;
  customer?: {
    name?: string | null;
    segment?: string | null;
    lifetime_value?: number;
    payment_method?: string | null;
  };
  transaction?: {
    amount?: number;
    payment_method?: string | null;
    device?: string | null;
    status?: string | null;
    failure_reason?: string | null;
    transaction_ref?: string | null;
    timestamp?: string | null;
  };
  strategies: Strategy[];
  actions: {
    id: number;
    action: string;
    tool: string;
    status: string;
    predicted_recovery: number;
    policy_checked: string;
    policy_result: string;
    detail: string;
    timestamp?: string | null;
  }[];
  trace: {
    id: number;
    case_id: number;
    agent: string;
    decision: string;
    reason: string;
    policy_checked: string;
    action: string;
    amount: number;
    timestamp: string;
  }[];
};

export type LearnedEntry = {
  strategy: string;
  attempts: number;
  successes: number;
  recovery_rate: number;
  amount_recovered: number;
};

export const statusColor: Record<string, string> = {
  open: "text-gold border-gold/40 bg-gold/5",
  approved: "text-gold border-gold/40 bg-gold/10",
  recovered: "text-gold border-gold/50 bg-gold/10",
  escalated: "text-danger border-danger/40 bg-danger/5",
  closed: "text-muted border-muted/30 bg-muted/5",
  stopped: "text-danger border-danger/40 bg-danger/5",
};

export const statusLabel: Record<string, string> = {
  open: "Open",
  approved: "Approved",
  recovered: "Recovered",
  escalated: "Escalated",
  closed: "Closed",
  stopped: "Stopped",
};
