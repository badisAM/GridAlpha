"use client";

import { useMemo, useState } from "react";

import Copilot from "@/components/Copilot";
import DispatchPanels, { type PanelRow } from "@/components/charts/DispatchPanels";
import { DriverBars, FrontierChart, PnlHistogram } from "@/components/charts/Small";
import { ChartCard, Hero, Legend, PageHeader, Segmented, Stat } from "@/components/ui";
import { C, SERIES } from "@/lib/colors";
import { eur, hourLabel, int, longDay, MODEL_LABEL, num, pct } from "@/lib/format";
import { useBacktestSummary, useBrief, useExplain, useForecast, usePlan } from "@/lib/hooks";

type Compare = "none" | "naive_d1" | "lgbm" | "tide";

export default function Desk() {
  const plan = usePlan();
  const fc = useForecast();
  const brief = useBrief();
  const explain = useExplain();
  const bt = useBacktestSummary();
  const [compare, setCompare] = useState<Compare>("naive_d1");

  const rows: PanelRow[] = useMemo(() => {
    if (!plan.data) return [];
    const byTs = new Map((fc.data?.hours ?? []).map((h) => [h.ts as string, h]));
    return plan.data.schedule.map((r) => {
      const h = byTs.get(r.ts);
      return {
        label: hourLabel(r.ts),
        q10: r.q10,
        q50: r.q50,
        q90: r.q90,
        band: [r.q10, r.q90] as [number, number],
        charge: r.charge,
        discharge: r.discharge,
        soc: r.soc,
        compare: compare !== "none" && h ? (h[`${compare}_q50`] as number) : null,
      };
    });
  }, [plan.data, fc.data, compare]);

  const p = plan.data;
  const f = brief.data?.facts as Record<string, number | string | null> | undefined;
  const cap = bt.data?.trading_metrics?.ensemble_cvar?.capture_ratio;
  const naiveCap = bt.data?.trading_metrics?.naive_d1?.capture_ratio;
  const energy = p?.battery?.energy_mwh ?? 20;

  return (
    <>
      <PageHeader
        title="Trading desk"
        subtitle={
          <>
            Day-ahead plan for <span className="font-medium text-ink">{longDay(p?.target_day)}</span> ·{" "}
            {num(p?.battery?.power_mw, 0)} MW / {num(energy, 0)} MWh battery · bids due before the 12:00 CET gate closure
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div className="sm:col-span-2">
          <Hero
            label="Expected P&L for the delivery day"
            value={eur(p?.expected_pnl)}
            sub={
              p?.risk && (
                <>
                  90 % of 100 scenarios above <b className="text-ink">{eur(p.risk.p5)}</b> · CVaR95 {eur(p.risk.cvar)} · P(loss){" "}
                  {pct(p.risk.prob_loss, 0)}
                </>
              )
            }
          />
        </div>
        <Stat label="Base price (P50)" value={`${num(f?.base_price as number)} €`} sub="€/MWh, daily mean" />
        <Stat label="Intraday spread" value={`${num(f?.spread as number, 0)} €`} sub={`peak ${f?.peak_hour ?? "—"} · trough ${f?.trough_hour ?? "—"}`} />
        <Stat label="Negative-price hours" value={int(f?.negative_hours_expected as number)} sub={(f?.negative_window as string) ?? "none expected"} />
        <Stat
          label="Backtest capture"
          value={pct(cap)}
          sub={<>of perfect-foresight revenue · naive {pct(naiveCap, 0)}</>}
          hint="Walk-forward: realised P&L / perfect-foresight P&L"
        />
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="Forecast, bid schedule and state of charge"
          subtitle={`Probabilistic ensemble (LightGBM + TiDE, conformal-calibrated) → mean-CVaR MILP · solved in ${num(p?.solve_ms, 0)} ms`}
          loading={plan.isLoading}
          error={plan.error}
          right={
            <Segmented<Compare>
              value={compare}
              onChange={setCompare}
              options={[
                { value: "none", label: "AI only" },
                { value: "naive_d1", label: "vs naive" },
                { value: "lgbm", label: "vs LGBM" },
                { value: "tide", label: "vs TiDE" },
              ]}
            />
          }
          legend={
            <Legend
              items={[
                { label: "AI forecast P50", color: C.s1 },
                { label: "P10–P90 band", color: C.s1, kind: "band" },
                ...(compare !== "none" ? [{ label: MODEL_LABEL[compare], color: SERIES[compare] }] : []),
                { label: "Discharge / sell", color: C.discharge, kind: "bar" as const },
                { label: "Charge / buy", color: C.charge, kind: "bar" as const },
              ]}
            />
          }
          table={{
            columns: ["Hour", "P10", "P50", "P90", "Charge MW", "Discharge MW", "SoC MWh"],
            rows: rows.map((r) => [r.label, num(r.q10), num(r.q50), num(r.q90), num(r.charge, 2), num(r.discharge, 2), num(r.soc, 1)]),
          }}
        >
          <DispatchPanels rows={rows} energyMwh={energy} compareKey={compare === "none" ? null : compare} />
        </ChartCard>
        <Copilot brief={brief.data} />
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <ChartCard
          title="Why this price? — top drivers"
          subtitle="Mean TreeSHAP contribution over the day, €/MWh vs the model baseline"
          loading={explain.isLoading}
          error={explain.error}
          legend={<Legend items={[{ label: "raises price", color: C.divPos, kind: "bar" }, { label: "lowers price", color: C.divNeg, kind: "bar" }]} />}
          table={{ columns: ["Driver", "Impact €/MWh"], rows: (explain.data?.drivers ?? []).map((d) => [d.feature, num(d.impact_eur_mwh)]) }}
        >
          <DriverBars drivers={explain.data?.drivers ?? []} />
        </ChartCard>
        <ChartCard
          title="Risk / return frontier"
          subtitle="Each point re-solves the MILP with a different risk aversion λ (highlighted: current)"
          loading={plan.isLoading}
          error={plan.error}
          table={{
            columns: ["λ", "Expected P&L", "CVaR95", "Cycles"],
            rows: (p?.frontier ?? []).map((x) => [x.risk_aversion, eur(x.expected_pnl), eur(x.cvar), num(x.cycles, 2)]),
          }}
        >
          <FrontierChart points={p?.frontier ?? []} current={p?.risk_aversion} />
        </ChartCard>
        <ChartCard
          title="P&L distribution over 100 price scenarios"
          subtitle="Gaussian-copula scenarios from the calibrated quantiles (hour-to-hour correlation estimated in backtest)"
          loading={plan.isLoading}
          error={plan.error}
          table={{ columns: ["From €", "To €", "Scenarios"], rows: (p?.scenario_pnl_hist ?? []).map((b) => [int(b.lo), int(b.hi), b.count]) }}
        >
          <PnlHistogram bins={p?.scenario_pnl_hist ?? []} expected={p?.expected_pnl} cvar={p?.risk?.cvar} />
        </ChartCard>
      </div>
    </>
  );
}
