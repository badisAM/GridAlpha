"use client";

import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import DispatchPanels, { type PanelRow } from "@/components/charts/DispatchPanels";
import { HBars } from "@/components/charts/Small";
import { AXIS, CURSOR, GRID, TipBox } from "@/components/charts/primitives";
import { Card, ChartCard, DataTable, Hero, Legend, PageHeader, Stat } from "@/components/ui";
import { C, SERIES } from "@/lib/colors";
import { compactEur, dayLabel, eur, hourLabel, int, MODEL_LABEL, num, pct } from "@/lib/format";
import { useBacktestDay, useBacktestDays, useBacktestSummary, useEquity, useMonthly } from "@/lib/hooks";

const ORDER = ["oracle", "ensemble_cvar", "ensemble", "lgbm", "tide", "profile7", "naive_d1"];
const PLOTTED = ["oracle", "ensemble_cvar", "lgbm", "tide", "profile7", "naive_d1"];

function EquityTip(props: { active?: boolean; label?: string | number; payload?: readonly { dataKey?: unknown; value?: unknown }[] }) {
  if (!props.active || !props.payload?.length) return null;
  const rows = [...props.payload]
    .sort((a, b) => Number(b.value) - Number(a.value))
    .map((p) => ({ name: MODEL_LABEL[String(p.dataKey)] ?? String(p.dataKey), value: eur(Number(p.value)), color: SERIES[String(p.dataKey)] }));
  return <TipBox title={`Cumulative P&L · ${props.label}`} rows={rows} />;
}

export default function Backtest() {
  const s = useBacktestSummary();
  const eq = useEquity();
  const monthly = useMonthly();
  const days = useBacktestDays();
  const [day, setDay] = useState<string>();
  useEffect(() => {
    if (!day && days.data?.length) setDay(days.data[days.data.length - 1]);
  }, [days.data, day]);
  const replay = useBacktestDay(day);

  const tm = s.data?.trading_metrics ?? {};
  const ai = tm.ensemble_cvar;
  const naive = tm.naive_d1;
  const scale = s.data?.battery?.power_mw ?? 10;
  const uplift = ai && naive ? (ai.eur_per_mw_year - naive.eur_per_mw_year) * scale : null;

  const eqData: Record<string, number | string>[] = useMemo(
    () => (eq.data ?? []).map((r) => ({ ...r, label: dayLabel(String(r.delivery_date)) })),
    [eq.data],
  );
  const last = eqData[eqData.length - 1];

  const rows: PanelRow[] = useMemo(() => {
    const r = replay.data;
    if (!r) return [];
    const sched = new Map(r.schedule.map((x) => [x.ts as string, x]));
    return r.forecast.map((f) => {
      const sc = sched.get(f.ts as string) ?? {};
      const net = Number(sc["net_ensemble_cvar"] ?? 0);
      return {
        label: hourLabel(f.ts as string),
        q10: Number(f.ensemble_q10),
        q50: Number(f.ensemble_q50),
        q90: Number(f.ensemble_q90),
        band: [Number(f.ensemble_q10), Number(f.ensemble_q90)] as [number, number],
        actual: f.actual == null ? null : Number(f.actual),
        charge: Math.max(0, -net),
        discharge: Math.max(0, net),
        soc: Number(sc["soc_ensemble_cvar"] ?? 0),
        compare: f.naive_d1_q50 == null ? null : Number(f.naive_d1_q50),
      };
    });
  }, [replay.data]);
  const dayPnl = new Map((replay.data?.pnl ?? []).map((p) => [p.strategy, p]));

  return (
    <>
      <PageHeader
        title="Walk-forward backtest"
        subtitle={
          <>
            {s.data ? `${s.data.period.start} → ${s.data.period.end} (${s.data.period.days} delivery days)` : "—"}. Models are re-trained on an expanding
            window, every schedule is committed before gate closure and settled at realised prices. Perfect foresight is the unreachable ceiling.
          </>
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2">
          <Hero
            label={`Extra revenue vs the naive desk, per year (${num(scale, 0)} MW battery)`}
            value={uplift == null ? "—" : `+${compactEur(uplift)}`}
            sub={ai && naive ? <>AI {eur(ai.eur_per_mw_year)}/MW/yr vs naive {eur(naive.eur_per_mw_year)}/MW/yr · same asset, same market, better decisions</> : null}
          />
        </div>
        <Stat label="Capture of perfect foresight" value={pct(ai?.capture_ratio)} sub={`naive D-1: ${pct(naive?.capture_ratio)}`} />
        <Stat label="Loss-making days" value={pct(ai?.loss_day_share, 1)} sub={`worst day ${eur(ai?.worst_day_eur)} · naive worst ${eur(naive?.worst_day_eur)}`} />
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="Cumulative P&L by strategy"
          subtitle="€, same battery, same days — only the forecast and decision layer differ"
          loading={eq.isLoading}
          error={eq.error}
          legend={<Legend items={PLOTTED.map((k) => ({ label: MODEL_LABEL[k], color: SERIES[k] }))} />}
          table={{ columns: ["Date", ...PLOTTED.map((k) => MODEL_LABEL[k])], rows: eqData.map((r) => [String(r.delivery_date), ...PLOTTED.map((k) => int(Number(r[k])))]) }}
        >
          <ResponsiveContainer width="100%" height={330}>
            <LineChart data={eqData} margin={{ top: 8, right: 90, bottom: 0, left: 8 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} minTickGap={50} />
              <YAxis {...AXIS} width={56} tickFormatter={(v) => compactEur(v)} />
              <Tooltip content={<EquityTip />} cursor={CURSOR} />
              {PLOTTED.map((k) => (
                <Line
                  key={k}
                  dataKey={k}
                  stroke={SERIES[k]}
                  strokeWidth={k === "ensemble_cvar" ? 2.5 : 1.5}
                  dot={false}
                  isAnimationActive={false}
                  label={(p: { index?: number; x?: number | string; y?: number | string }) =>
                    (k === "ensemble_cvar" || k === "naive_d1" || k === "oracle") && p.index === eqData.length - 1 ? (
                      <text key={k} x={Number(p.x ?? 0) + 6} y={Number(p.y ?? 0) + 4} fontSize={11} fill="var(--ink-2)">
                        {k === "oracle" ? "ceiling" : k === "naive_d1" ? "naive" : "AI"} {compactEur(Number(last?.[k]))}
                      </text>
                    ) : (
                      <g key={`${k}-${p.index}`} />
                    )
                  }
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="Capture ratio"
          subtitle="Realised P&L ÷ perfect-foresight P&L"
          loading={s.isLoading}
          error={s.error}
          table={{ columns: ["Strategy", "Capture"], rows: ORDER.filter((k) => tm[k] && k !== "oracle").map((k) => [MODEL_LABEL[k], pct(tm[k].capture_ratio)]) }}
        >
          <HBars
            data={ORDER.filter((k) => tm[k] && k !== "oracle").map((k) => ({ name: MODEL_LABEL[k], v: tm[k].capture_ratio * 100 }))}
            format={(v) => `${num(v, 1)} %`}
            height={300}
          />
        </ChartCard>
      </div>

      <Card className="mt-3 p-4">
        <h2 className="mb-3 text-sm font-semibold">Strategy scorecard</h2>
        <DataTable
          columns={["Strategy", "P&L", "€/MW/yr", "Capture", "Worst day", "CVaR 5 % day", "Loss days", "Max drawdown", "Cycles/day"]}
          rows={ORDER.filter((k) => tm[k]).map((k) => {
            const m = tm[k];
            return [
              <span key={k} className="inline-flex items-center gap-2">
                <span className="h-0.5 w-3 rounded-full" style={{ background: SERIES[k] }} />
                {MODEL_LABEL[k]}
              </span>,
              eur(m.total_pnl_eur),
              eur(m.eur_per_mw_year),
              pct(m.capture_ratio),
              eur(m.worst_day_eur),
              eur(m.cvar5_day_eur),
              pct(m.loss_day_share),
              eur(m.max_drawdown_eur),
              num(m.avg_cycles_per_day, 2),
            ];
          })}
        />
      </Card>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="Replay a delivery day"
          subtitle="What the AI forecast, what it committed, and what the market actually cleared at"
          loading={replay.isLoading}
          error={replay.error}
          right={
            <select
              value={day ?? ""}
              onChange={(e) => setDay(e.target.value)}
              className="h-7 rounded-md border border-line bg-surface-2 px-2 text-xs text-ink"
              aria-label="Delivery day"
            >
              {[...(days.data ?? [])].reverse().map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          }
          legend={
            <Legend
              items={[
                { label: "Realised price", color: C.ink },
                { label: "AI forecast P50", color: C.s1 },
                { label: "P10–P90", color: C.s1, kind: "band" },
                { label: "Naive D-1", color: SERIES.naive_d1 },
                { label: "Discharge", color: C.discharge, kind: "bar" },
                { label: "Charge", color: C.charge, kind: "bar" },
              ]}
            />
          }
        >
          <DispatchPanels rows={rows} energyMwh={s.data?.battery?.energy_mwh ?? 20} compareKey="naive_d1" syncId="replay" height={220} />
        </ChartCard>
        <Card className="p-4">
          <h2 className="text-sm font-semibold">P&L on {day ?? "—"}</h2>
          <p className="mt-0.5 text-xs text-ink-2">Settled at the realised day-ahead prices</p>
          <div className="mt-3">
            <DataTable
              columns={["Strategy", "Realised", "Expected"]}
              rows={ORDER.filter((k) => dayPnl.has(k)).map((k) => {
                const p = dayPnl.get(k)!;
                return [MODEL_LABEL[k], eur(p.pnl), eur(p.expected_pnl)];
              })}
            />
          </div>
          <h3 className="mt-5 mb-2 text-sm font-semibold">Monthly P&L</h3>
          <DataTable
            columns={["Month", "AI", "Naive", "AI capture"]}
            rows={(monthly.data ?? []).map((m) => [
              String(m.month),
              compactEur(Number(m.ensemble_cvar)),
              compactEur(Number(m.naive_d1)),
              pct(Number(m.ensemble_cvar_capture)),
            ])}
            maxHeight={260}
          />
        </Card>
      </div>
      <p className="mt-3 text-xs text-muted">
        Assumptions: price-taker self-schedule on the day-ahead auction, energy-neutral days (SoC returns to 50 %), degradation cost per MWh
        discharged, hourly MTU. Perfect foresight uses the realised prices and is not achievable.
      </p>
    </>
  );
}
