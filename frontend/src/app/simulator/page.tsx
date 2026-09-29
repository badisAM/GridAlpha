"use client";

import { Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import DispatchPanels, { type PanelRow } from "@/components/charts/DispatchPanels";
import { FrontierChart, PnlHistogram } from "@/components/charts/Small";
import { Card, ChartCard, ErrorState, Legend, PageHeader, SliderField, Stat } from "@/components/ui";
import { post, type FrontierPoint, type PlanResponse } from "@/lib/api";
import { C } from "@/lib/colors";
import { eur, hourLabel, MODEL_LABEL, num, pct } from "@/lib/format";
import { useBacktestDays } from "@/lib/hooks";

type Model = "ensemble" | "lgbm" | "tide" | "profile7" | "naive_d1";

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function Simulator() {
  const days = useBacktestDays();
  const [day, setDay] = useState("latest");
  const [model, setModel] = useState<Model>("ensemble");
  const [power, setPower] = useState(10);
  const [duration, setDuration] = useState(2);
  const [rte, setRte] = useState(0.88);
  const [cycles, setCycles] = useState(1.5);
  const [deg, setDeg] = useState(8);
  const [lam, setLam] = useState(0.1);

  const body = useMemo(
    () => ({
      day,
      model,
      power_mw: power,
      energy_mwh: power * duration,
      rte,
      max_cycles_per_day: cycles,
      degradation_eur_per_mwh: deg,
      risk_aversion: lam,
    }),
    [day, model, power, duration, rte, cycles, deg, lam],
  );
  const req = useDebounced(body);
  const [res, setRes] = useState<PlanResponse | null>(null);
  const [frontier, setFrontier] = useState<FrontierPoint[]>([]);
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [rtt, setRtt] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    const t0 = performance.now();
    Promise.all([post<PlanResponse>("/trading/optimize", req), post<{ points: FrontierPoint[] }>("/trading/frontier", req)])
      .then(([r, f]) => {
        if (!alive) return;
        setRes(r);
        setFrontier(f.points);
        setErr(null);
        setRtt(performance.now() - t0);
      })
      .catch((e) => alive && setErr(e))
      .finally(() => alive && setBusy(false));
    return () => {
      alive = false;
    };
  }, [req]);

  const rows: PanelRow[] = useMemo(
    () =>
      (res?.schedule ?? []).map((r) => ({
        label: hourLabel(r.ts),
        q10: r.q10,
        q50: r.q50,
        q90: r.q90,
        band: [r.q10, r.q90] as [number, number],
        actual: r.actual ?? null,
        charge: r.charge,
        discharge: r.discharge,
        soc: r.soc,
      })),
    [res],
  );
  const past = res?.realised_pnl != null;

  return (
    <>
      <PageHeader
        title="What-if simulator"
        subtitle="Size the asset, pick a forecaster and a risk appetite — the MILP re-optimises live on every change. Pick a past day to see the realised P&L against perfect foresight."
        right={busy ? <span className="inline-flex items-center gap-1.5 text-xs text-ink-2"><Loader2 size={13} className="animate-spin" /> optimising…</span> : rtt != null ? <span className="text-xs text-muted tabular">round-trip {num(rtt, 0)} ms · solver {num(res?.solve_ms, 0)} ms</span> : null}
      />
      <div className="grid gap-3 xl:grid-cols-[300px_1fr]">
        <Card className="h-fit space-y-5 p-4 xl:sticky xl:top-20">
          <div>
            <div className="mb-1 text-xs text-ink-2">Delivery day</div>
            <select value={day} onChange={(e) => setDay(e.target.value)} className="h-8 w-full rounded-md border border-line bg-surface-2 px-2 text-sm">
              <option value="latest">Next delivery day (forecast)</option>
              {[...(days.data ?? [])].reverse().map((d) => (
                <option key={d} value={d}>
                  {d} (settled)
                </option>
              ))}
            </select>
          </div>
          <div>
            <div className="mb-1 text-xs text-ink-2">Forecast model</div>
            <select value={model} onChange={(e) => setModel(e.target.value as Model)} className="h-8 w-full rounded-md border border-line bg-surface-2 px-2 text-sm">
              {(["ensemble", "lgbm", "tide", "profile7", "naive_d1"] as Model[]).map((m) => (
                <option key={m} value={m}>
                  {MODEL_LABEL[m]}
                </option>
              ))}
            </select>
          </div>
          <SliderField label="Power" value={power} min={1} max={100} step={1} onChange={setPower} format={(v) => `${v} MW`} />
          <SliderField label="Duration" value={duration} min={1} max={4} step={0.5} onChange={setDuration} format={(v) => `${v} h · ${num(v * power, 0)} MWh`} />
          <SliderField label="Round-trip efficiency" value={rte} min={0.75} max={0.95} step={0.01} onChange={setRte} format={(v) => pct(v, 0)} />
          <SliderField label="Max cycles per day" value={cycles} min={0.5} max={3} step={0.25} onChange={setCycles} format={(v) => num(v, 2)} hint="Warranty throughput limit" />
          <SliderField label="Degradation cost" value={deg} min={0} max={30} step={1} onChange={setDeg} format={(v) => `${v} €/MWh`} hint="Cell wear per MWh discharged" />
          <div>
            <SliderField label="Risk aversion λ" value={lam} min={0} max={0.9} step={0.1} onChange={setLam} format={(v) => num(v, 1)} hint="0 = maximise expected P&L · higher = protect the worst 5 % of scenarios (CVaR)" />
            <div className="mt-1 flex justify-between text-[10px] text-muted">
              <span>risk-neutral</span>
              <span>CVaR-averse</span>
            </div>
          </div>
        </Card>

        <div className="min-w-0 space-y-3">
          {err ? (
            <Card className="p-4">
              <ErrorState error={err} />
            </Card>
          ) : null}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Expected P&L" value={eur(res?.expected_pnl)} sub={`${num(res?.cycles, 2)} cycles · ${num(res?.energy_sold_mwh, 1)} MWh sold`} />
            <Stat label="CVaR 95 % (worst 5 % of scenarios)" value={eur(res?.risk?.cvar)} sub={`P5 ${eur(res?.risk?.p5)} · P(loss) ${pct(res?.risk?.prob_loss, 0)}`} />
            {past ? (
              <>
                <Stat label="Realised P&L" value={eur(res?.realised_pnl)} sub="settled at cleared prices" />
                <Stat label="Capture vs perfect foresight" value={pct(res?.capture_ratio ?? null)} sub={`ceiling ${eur(res?.oracle_pnl)}`} />
              </>
            ) : (
              <>
                <Stat label="Revenue per MW" value={eur(res ? res.expected_pnl / power : null)} sub="expected, this day" />
                <Stat label="Annualised (× 365)" value={eur(res ? (res.expected_pnl / power) * 365 : null)} sub="€/MW/yr at today's spread — indicative" />
              </>
            )}
          </div>
          <ChartCard
            title={`Schedule · ${res?.day ?? "—"} · ${MODEL_LABEL[model]}`}
            subtitle={past ? "Past day: the plan was built on the forecast only, then settled at realised prices (black line)" : "Next delivery day: forecast-based plan"}
            legend={
              <Legend
                items={[
                  { label: "Forecast P50", color: C.s1 },
                  { label: "P10–P90", color: C.s1, kind: "band" },
                  ...(past ? [{ label: "Realised", color: C.ink }] : []),
                  { label: "Discharge", color: C.discharge, kind: "bar" as const },
                  { label: "Charge", color: C.charge, kind: "bar" as const },
                ]}
              />
            }
            table={{ columns: ["Hour", "P50", "Charge", "Discharge", "SoC"], rows: rows.map((r) => [r.label, num(r.q50), num(r.charge, 2), num(r.discharge, 2), num(r.soc, 1)]) }}
          >
            <div className={busy ? "opacity-60 transition-opacity" : "transition-opacity"}>
              <DispatchPanels rows={rows} energyMwh={power * duration} syncId="sim" height={220} />
            </div>
          </ChartCard>
          <div className="grid gap-3 lg:grid-cols-2">
            <ChartCard title="Risk / return frontier" subtitle="Expected P&L vs CVaR 95 % for λ ∈ [0, 0.9]" table={{ columns: ["λ", "E[P&L]", "CVaR"], rows: frontier.map((f) => [f.risk_aversion, eur(f.expected_pnl), eur(f.cvar)]) }}>
              <FrontierChart points={frontier} current={lam} />
            </ChartCard>
            <ChartCard title="Scenario P&L distribution" subtitle="100 correlated price scenarios, same schedule" table={{ columns: ["From", "To", "n"], rows: (res?.scenario_pnl_hist ?? []).map((b) => [eur(b.lo), eur(b.hi), b.count]) }}>
              <PnlHistogram bins={res?.scenario_pnl_hist ?? []} expected={res?.expected_pnl} cvar={res?.risk?.cvar} />
            </ChartCard>
          </div>
        </div>
      </div>
    </>
  );
}

