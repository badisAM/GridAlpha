"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  get,
  type BacktestSummary,
  type Brief,
  type ForecastLatest,
  type Health,
  type MarketSummary,
  type PipelineRun,
  type PlanResponse,
  type Scorecard,
} from "./api";

// keepPreviousData: on refetch the last render stays (no skeleton flash)
const useQ = <T,>(key: unknown[], path: string, refetchInterval?: number) =>
  useQuery<T>({ queryKey: key, queryFn: () => get<T>(path), placeholderData: keepPreviousData, refetchInterval });

export const useHealth = () => useQ<Health>(["health"], "/health", 15_000);
export const useForecast = () => useQ<ForecastLatest>(["forecast"], "/forecast/latest");
export const usePlan = () => useQ<PlanResponse>(["plan"], "/trading/plan");
export const useBrief = () => useQ<Brief>(["brief"], "/copilot/brief");
export const useExplain = () =>
  useQ<{
    target_day: string;
    features: string[];
    hourly: Record<string, number | string>[];
    drivers: { feature: string; impact_eur_mwh: number; value: number | null }[];
    global_importance: { feature: string; share_pct: number }[];
  }>(["explain"], "/forecast/explain");
export const useBacktestSummary = () => useQ<BacktestSummary>(["bt-summary"], "/backtest/summary");
export const useEquity = () => useQ<Record<string, number | string>[]>(["bt-equity"], "/backtest/equity");
export const useMonthly = () => useQ<Record<string, number | string>[]>(["bt-monthly"], "/backtest/monthly");
export const useWeights = () => useQ<Record<string, number | string>[]>(["bt-weights"], "/backtest/weights");
export const useBacktestDays = () => useQ<string[]>(["bt-days"], "/backtest/days");
export const useScorecard = () => useQ<Scorecard>(["kpis"], "/business/kpis", 30_000);
export const useMarketSummary = () => useQ<MarketSummary>(["mkt-summary"], "/market/summary");
export const useMarketPrices = (days: number) =>
  useQ<{ ts: string; hour: number; price: number | null; load: number; solar: number; wind: number }[]>(
    ["mkt-prices", days],
    `/market/prices?days=${days}`,
  );
export const useMarketDaily = (days = 365) =>
  useQ<{ date: string; mean: number; min: number; max: number; spread: number; neg_hours: number; solar_gwh: number; wind_gwh: number; load_gwh: number }[]>(
    ["mkt-daily", days],
    `/market/daily?days=${days}`,
  );
export const useProfile = () => useQ<{ year: number; months: number[]; matrix: (number | null)[][] }>(["mkt-profile"], "/market/profile");
export const useLeaderboard = () =>
  useQ<(Record<string, number | null> & { model: string })[]>(["leaderboard"], "/models/leaderboard");
export const useErrorByHour = () => useQ<Record<string, number>[]>(["err-hour"], "/models/error-by-hour");
export const useCalibration = () =>
  useQ<{ model: string; points: { nominal: number; empirical: number }[] }[]>(["calibration"], "/models/calibration");
export const useRegistry = () =>
  useQ<{ champion: string | null; versions: Record<string, unknown>[]; champion_card: Record<string, unknown> }>(
    ["registry"],
    "/models",
  );
export const useDrift = () =>
  useQ<{
    data: { feature: string; metric: string; value: number | null; status: string; ref_mean: number | null; cur_mean: number | null }[];
    performance: {
      overall_mae: number;
      recent_mae: number;
      mae_ratio: number;
      recent_coverage: number;
      status: string;
      retrain_recommended: boolean;
      window_days: number;
      series: { date: string; mae: number; coverage: number }[];
    };
  }>(["drift"], "/monitoring/drift");
export const useDataQuality = () =>
  useQ<{
    mode: string;
    requested_mode: string;
    fetched_at: string;
    sources: Record<string, string>;
    fallback_reason?: string;
    last_price_ts: string;
    rows: number;
    status: string;
    checks: { column: string; coverage: number; out_of_range: number; longest_gap_h: number; staleness_h: number | null; optional: boolean; status: string }[];
  }>(["dq"], "/monitoring/data-quality");
export const useLatency = () =>
  useQ<{ count: number; p50_ms: number | null; p95_ms: number | null; p99_ms: number | null; routes: { route: string; count: number; p50_ms: number; p95_ms: number; p99_ms: number }[] }>(
    ["latency"],
    "/monitoring/latency",
    5_000,
  );
export const usePipelineRuns = (poll = false) => useQ<PipelineRun[]>(["runs"], "/monitoring/pipeline", poll ? 3_000 : 30_000);
export const useBacktestDay = (day: string | undefined) =>
  useQuery({
    queryKey: ["bt-day", day],
    queryFn: () =>
      get<{
        day: string;
        forecast: Record<string, number | string | null>[];
        schedule: Record<string, number | string | null>[];
        pnl: { strategy: string; pnl: number; expected_pnl: number; cycles: number; solve_ms: number }[];
      }>(`/backtest/day/${day}`),
    enabled: !!day,
    placeholderData: keepPreviousData,
  });
