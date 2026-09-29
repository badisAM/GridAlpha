// Typed client for the GridAlpha FastAPI backend (proxied under /api).

export const API = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {}
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {}
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export function wsUrl(path: string): string {
  const env = process.env.NEXT_PUBLIC_WS_URL;
  if (env) return `${env}${path}`;
  if (typeof window === "undefined") return `ws://localhost:8000${path}`;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.hostname}:8000${path}`;
}

// ---------------------------------------------------------------- types
export type Health = {
  status: string;
  version: string;
  data_mode: "live" | "synthetic" | null;
  model_version: string | null;
  target_day: string | null;
  last_run: { run_id: string; status: string; finished_at: string; duration_s: number } | null;
  pipeline_running: boolean;
};

export type Quant = { q10: number; q50: number; q90: number };

export type ForecastLatest = {
  target_day: string;
  generated_at: string;
  model_version: string;
  ensemble_weights: Record<string, number>;
  conformal_scale: number;
  drivers: Driver[];
  global_importance: { feature: string; share_pct: number }[];
  models: string[];
  hours: Record<string, number | string | null>[];
};

export type Driver = { feature: string; impact_eur_mwh: number; value: number | null };

export type Risk = { p5?: number; p50?: number; p95?: number; cvar?: number; prob_loss?: number };

export type ScheduleRow = {
  ts: string;
  hour: number;
  q10: number;
  q50: number;
  q90: number;
  charge: number;
  discharge: number;
  net: number;
  soc: number;
  actual?: number;
};

export type PlanResponse = {
  expected_pnl: number;
  risk: Risk;
  cycles: number;
  energy_bought_mwh: number;
  energy_sold_mwh: number;
  solve_ms: number;
  status: string;
  risk_aversion: number;
  battery: Record<string, number>;
  scenario_pnl_hist: { lo: number; hi: number; count: number }[];
  frontier?: FrontierPoint[];
  target_day?: string;
  day?: string;
  realised_pnl?: number;
  oracle_pnl?: number;
  capture_ratio?: number | null;
  schedule: ScheduleRow[];
};

export type FrontierPoint = { risk_aversion: number; expected_pnl: number; cvar: number; cycles: number };

export type Brief = {
  generated_at: string;
  generated_by: string;
  text: string;
  facts: Record<string, unknown>;
  alerts: { level: string; code: string; message: string }[];
};

export type TradingMetrics = {
  days: number;
  total_pnl_eur: number;
  eur_per_mw_year: number;
  capture_ratio: number;
  daily_pnl_std_eur: number;
  cvar5_day_eur: number;
  max_drawdown_eur: number;
  worst_day_eur: number;
  loss_day_share: number;
  avg_cycles_per_day: number;
  forecast_bias_eur: number;
};

export type ForecastMetrics = {
  n_hours: number;
  mae: number;
  rmse: number;
  bias: number;
  pinball: number;
  coverage_80: number;
  interval_width: number;
  kendall_tau: number;
  peak_hour_hit: number;
  trough_hour_hit: number;
  neg_price_recall: number;
  spike_mae: number;
};

export type BacktestSummary = {
  period: { start: string; end: string; days: number };
  battery: Record<string, number>;
  config: Record<string, unknown>;
  forecast_metrics: Record<string, ForecastMetrics>;
  trading_metrics: Record<string, TradingMetrics>;
  latest_weights: Record<string, number>;
  copula_rho: number;
  timings_s: Record<string, number>;
  avg_solve_ms: number;
};

export type Objective = {
  id: string;
  objective: string;
  kpi: string;
  target: string;
  value: number | null;
  fmt: "pct" | "eur" | "ms" | "seconds" | "num";
  extra?: number | null;
  status: "pass" | "miss" | "n/a";
};

export type Scorecard = {
  generated_at: string;
  period: { start: string; end: string; days: number };
  business_objectives: Objective[];
  data_science_objectives: Objective[];
  uplift_eur_per_year: number;
};

export type MarketSummary = {
  last_delivery_day: string;
  mean_30d: number;
  mean_prev_30d: number;
  min_30d: number;
  max_30d: number;
  vol_30d: number;
  avg_daily_spread_30d: number;
  avg_daily_spread_prev_30d: number;
  neg_hours_30d: number;
  neg_hours_ytd: number;
  mean_ytd: number;
  renewable_share_30d: number;
  last_day_curve: { hour: number; price: number }[];
};

export type PipelineRun = {
  run_id: string;
  started_at: string;
  finished_at?: string;
  duration_s?: number;
  status: string;
  data_mode?: string;
  target_day?: string;
  quick?: boolean;
  steps: Record<string, number>;
  error?: string;
};

export type Tick = {
  type: "tick";
  i: number;
  ts: string;
  local: string;
  price: number;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  action: "CHARGE" | "DISCHARGE" | "IDLE";
  mw: number;
  soc: number;
  pnl_ai: number;
  pnl_naive: number | null;
};
