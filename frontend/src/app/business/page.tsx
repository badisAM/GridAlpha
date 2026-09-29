"use client";

import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS, CURSOR, GRID, makeTip } from "@/components/charts/primitives";
import { Card, ChartCard, Hero, PageHeader, SliderField, Stat, StatusPill } from "@/components/ui";
import { post, type Objective } from "@/lib/api";
import { C } from "@/lib/colors";
import { compactEur, eur, num, pct } from "@/lib/format";
import { useBacktestSummary, useScorecard } from "@/lib/hooks";

function fmt(o: Objective) {
  const v = o.value;
  if (v == null) return "—";
  switch (o.fmt) {
    case "pct":
      return pct(v);
    case "eur":
      return eur(v);
    case "ms":
      return `${num(v, 1)} ms`;
    case "seconds":
      return `${num(v, 0)} s`;
    default:
      return num(v, 3);
  }
}

type Inv = {
  capex_eur: number;
  npv_eur: number;
  irr: number | null;
  payback_years: number | null;
  year1_revenue_eur: number;
  cashflows: { year: number; revenue: number; opex: number; cumulative: number }[];
};

function ObjectiveList({ items, extraLabel }: { items: Objective[]; extraLabel: (o: Objective) => string | null }) {
  return (
    <ul className="divide-y divide-line rounded-lg border border-line">
      {items.map((o) => (
        <li key={o.id} className="grid grid-cols-[44px_1fr_auto] items-center gap-3 px-3 py-2.5 sm:grid-cols-[44px_1fr_190px_130px_110px]">
          <span className="font-mono text-xs text-muted">{o.id}</span>
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink">{o.objective}</div>
            <div className="text-xs text-ink-2">{o.kpi}</div>
          </div>
          <div className="hidden text-right text-xs text-ink-2 sm:block">
            target <span className="text-ink">{o.target}</span>
          </div>
          <div className="hidden text-right sm:block">
            <div className="text-sm font-semibold tabular">{fmt(o)}</div>
            {extraLabel(o) && <div className="text-[11px] text-muted">{extraLabel(o)}</div>}
          </div>
          <div className="justify-self-end">
            <StatusPill status={o.status} />
          </div>
          <div className="col-span-3 -mt-1 flex gap-3 text-xs text-ink-2 sm:hidden">
            <span>target {o.target}</span>
            <span className="font-semibold text-ink">{fmt(o)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

const CONTEXT = [
  ["Negative day-ahead hours in Germany, 2025", "≈ 573 h (record; 457 h in 2024)", "Bloomberg / Montel"],
  ["Average daily price spread DE, 2025", "≈ 130 €/MWh", "FfE, EPEX Spot analysis"],
  ["Record low day-ahead price", "−250 €/MWh (11 May 2025)", "FfE"],
  ["Grid-scale batteries in Germany, end 2025", "2.4 GW / 3.5 GWh; ~5.6 GW due 2026–27", "Modo Energy"],
  ["All-in BESS capex outside China/US, Oct 2025", "≈ $125/kWh (large 4 h projects)", "Ember"],
  ["Forecast-driven arbitrage capture (literature)", "~66–98 % of perfect foresight", "arXiv 2604.12082, Energies 18(13)"],
];

export default function Business() {
  const sc = useScorecard();
  const bt = useBacktestSummary();
  const [capex, setCapex] = useState(180);
  const [duration, setDuration] = useState(2);
  const [life, setLife] = useState(15);
  const [rate, setRate] = useState(0.08);
  const [decline, setDecline] = useState(0.02);
  const [inv, setInv] = useState<Inv | null>(null);
  const [invNaive, setInvNaive] = useState<Inv | null>(null);

  useEffect(() => {
    const body = { power_mw: 10, duration_h: duration, capex_eur_per_kwh: capex, lifetime_years: life, discount_rate: rate, revenue_decline_pct: decline };
    const t = setTimeout(() => {
      post<Inv>("/business/investment", { ...body, strategy: "ensemble_cvar" }).then(setInv).catch(() => setInv(null));
      post<Inv>("/business/investment", { ...body, strategy: "naive_d1" }).then(setInvNaive).catch(() => setInvNaive(null));
    }, 200);
    return () => clearTimeout(t);
  }, [capex, duration, life, rate, decline]);

  const Tip = makeTip<{ year: number; cumulative: number; revenue: number }>(
    (d) => `Year ${d.year}`,
    (d) => [
      { name: "Cumulative cash (AI)", value: eur(d.cumulative), color: C.s1 },
      { name: "Revenue that year", value: eur(d.revenue) },
    ],
  );
  const tm = bt.data?.trading_metrics;
  const bo3 = sc.data?.business_objectives.find((o) => o.id === "BO3");

  return (
    <>
      <PageHeader
        title="Business case"
        subtitle="Why this project matters: Germany's power prices swing harder every year (solar at noon, scarcity in the evening), batteries are being built at record pace, and every percentage point of arbitrage captured is cash. GridAlpha automates the daily forecast → bid loop and measures its value in euros."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <Hero
            label="Measured value of the AI decision layer (10 MW battery, per year)"
            value={sc.data ? `+${compactEur(sc.data.uplift_eur_per_year)}` : "—"}
            sub={<>vs a desk scheduling on yesterday&apos;s prices — from the walk-forward backtest {sc.data ? `${sc.data.period.start} → ${sc.data.period.end}` : ""}</>}
          />
        </div>
        <Stat
          label="Daily bidding workflow, automated"
          value={bo3?.value != null ? `${num(bo3.value / 60, 1)} min` : "—"}
          sub="scrape → forecast → optimise → brief (last run) · replaces a manual data-pull + spreadsheet routine"
        />
        <Stat label="Decision latency" value={`${num(bt.data?.avg_solve_ms, 0)} ms`} sub="MILP solve per day · 100 scenarios" />
      </div>

      <div className="mt-3 grid gap-3">
        <Card className="p-4">
          <h2 className="mb-1 text-sm font-semibold">Business objectives (BO)</h2>
          <p className="mb-3 text-xs text-ink-2">Targets set before modelling; values recomputed at every pipeline run.</p>
          <ObjectiveList
            items={sc.data?.business_objectives ?? []}
            extraLabel={(o) => (o.id === "BO2" && o.extra != null ? `+${compactEur(o.extra)} / year` : o.id === "BO5" && o.extra != null ? `ceiling ${eur(o.extra)}` : o.id === "BO3" && o.extra != null ? `${pct(o.extra, 0)} runs succeeded` : null)}
          />
        </Card>
        <Card className="p-4">
          <h2 className="mb-1 text-sm font-semibold">Data-science objectives (DSO)</h2>
          <p className="mb-3 text-xs text-ink-2">Each DSO is the measurable lever behind a BO (e.g. ranking quality τ → capture ratio → revenue).</p>
          <ObjectiveList
            items={sc.data?.data_science_objectives ?? []}
            extraLabel={(o) => (o.id === "DSO3" && o.extra != null ? `naive ${num(o.extra, 3)}` : o.id === "DSO1" && o.extra != null ? `MAE ${num(o.extra, 1)} €/MWh` : null)}
          />
        </Card>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-[320px_1fr]">
        <Card className="h-fit space-y-5 p-4">
          <div>
            <h2 className="text-sm font-semibold">Investment calculator</h2>
            <p className="mt-0.5 text-xs text-ink-2">10 MW battery, revenue = backtested €/MW/yr (day-ahead arbitrage only — no ancillary services stacked).</p>
          </div>
          <SliderField label="All-in capex" value={capex} min={80} max={400} step={10} onChange={setCapex} format={(v) => `${v} €/kWh`} hint="Ember: ≈ $125/kWh for large 4 h projects (Oct 2025)" />
          <SliderField label="Duration" value={duration} min={1} max={4} step={0.5} onChange={setDuration} format={(v) => `${v} h`} />
          <SliderField label="Lifetime" value={life} min={8} max={25} step={1} onChange={setLife} format={(v) => `${v} years`} />
          <SliderField label="Discount rate (WACC)" value={rate} min={0.03} max={0.15} step={0.005} onChange={setRate} format={(v) => pct(v, 1)} />
          <SliderField label="Revenue decline / year" value={decline} min={0} max={0.08} step={0.005} onChange={setDecline} format={(v) => pct(v, 1)} hint="capacity fade + spread cannibalisation" />
          <p className="text-[11px] text-muted">Duration changes capex; revenue per MW is kept at the backtested 2 h value (conservative for longer batteries).</p>
        </Card>
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="NPV · AI strategy" value={compactEur(inv?.npv_eur)} sub={`naive desk ${compactEur(invNaive?.npv_eur)}`} deltaGood />
            <Stat label="IRR" value={inv?.irr == null ? "—" : pct(inv.irr)} sub={`naive ${invNaive?.irr == null ? "—" : pct(invNaive.irr)}`} />
            <Stat label="Payback" value={inv?.payback_years == null ? "> lifetime" : `${num(inv.payback_years, 1)} y`} sub={`naive ${invNaive?.payback_years == null ? "> lifetime" : `${num(invNaive.payback_years, 1)} y`}`} />
            <Stat label="Capex" value={compactEur(inv?.capex_eur)} sub={`year-1 revenue ${compactEur(inv?.year1_revenue_eur)}`} />
          </div>
          <ChartCard
            title="Cumulative cash flow"
            subtitle="Undiscounted, € — the break-even year is the payback"
            table={{ columns: ["Year", "Revenue", "Opex", "Cumulative"], rows: (inv?.cashflows ?? []).map((c) => [c.year, eur(c.revenue), eur(c.opex), eur(c.cumulative)]) }}
          >
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={inv?.cashflows ?? []} margin={{ top: 6, right: 8, bottom: 0, left: 8 }}>
                <CartesianGrid {...GRID} />
                <XAxis dataKey="year" {...AXIS} />
                <YAxis {...AXIS} width={60} tickFormatter={(v) => compactEur(v)} />
                <ReferenceLine y={0} stroke="var(--axis)" />
                <Tooltip content={<Tip />} cursor={CURSOR} />
                <Area dataKey="cumulative" stroke={C.s1} strokeWidth={2} fill={C.s1} fillOpacity={0.1} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">Market context (sourced)</h2>
          <dl className="divide-y divide-line rounded-lg border border-line">
            {CONTEXT.map(([fact, value, src]) => (
              <div key={fact} className="grid gap-1 px-3 py-2.5 sm:grid-cols-[1fr_auto] sm:items-center sm:gap-4">
                <dt className="text-sm text-ink-2">{fact}</dt>
                <dd className="text-sm font-medium text-ink sm:text-right">
                  {value}
                  <span className="block text-[11px] font-normal text-muted">{src}</span>
                </dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">What gets automated</h2>
          <ol className="space-y-2 text-sm text-ink-2">
            {[
              ["Scrape", "prices & generation (Energy-Charts), weather forecasts for 8 sites (Open-Meteo), TTF gas (Yahoo) — cached, retried, quality-gated"],
              ["Forecast", "LightGBM quantiles + TiDE deep model → online ensemble → adaptive conformal calibration, explained with TreeSHAP"],
              ["Decide", "100 correlated price scenarios → mean-CVaR MILP (HiGHS) respecting power, energy, efficiency, cycles and degradation"],
              ["Control", "walk-forward backtest, champion/challenger registry, drift & latency monitoring, daily 10:30 CET scheduler"],
              ["Explain", "copilot brief with alerts (negative prices, wide spreads, uncertainty) for the trader who signs the bid"],
            ].map(([k, v], i) => (
              <li key={k} className="flex gap-3">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent">{i + 1}</span>
                <span>
                  <b className="text-ink">{k}</b> — {v}
                </span>
              </li>
            ))}
          </ol>
          {tm && (
            <p className="mt-4 border-t border-line pt-3 text-xs text-ink-2">
              Backtest: AI captures <b className="text-ink">{pct(tm.ensemble_cvar?.capture_ratio)}</b> of the perfect-foresight ceiling vs{" "}
              <b className="text-ink">{pct(tm.naive_d1?.capture_ratio)}</b> for the naive schedule and {pct(tm.profile7?.capture_ratio)} for a 7-day average profile.
            </p>
          )}
        </Card>
      </div>
    </>
  );
}
