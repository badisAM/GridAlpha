"use client";

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { AXIS, CURSOR, GRID, makeTip } from "@/components/charts/primitives";
import { ChartCard, Legend, PageHeader, Segmented, Stat } from "@/components/ui";
import { C } from "@/lib/colors";
import { dayHourLabel, dayLabel, int, num, signedPct } from "@/lib/format";
import { useMarketDaily, useMarketPrices, useMarketSummary, useProfile } from "@/lib/hooks";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function Heatmap({ months, matrix }: { months: number[]; matrix: (number | null)[][] }) {
  const flat = matrix.flat().filter((v): v is number => v != null);
  const lo = Math.min(...flat, 0);
  const hi = Math.max(...flat, 1);
  const [hover, setHover] = useState<{ m: number; h: number; v: number } | null>(null);
  return (
    <div>
      <div className="overflow-x-auto">
        <div className="grid min-w-[640px] gap-[2px]" style={{ gridTemplateColumns: `36px repeat(24, minmax(0, 1fr))` }}>
          <div />
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="text-center text-[10px] text-muted tabular">
              {h % 3 === 0 ? h : ""}
            </div>
          ))}
          {matrix.map((row, i) => (
            <div key={i} className="contents">
              <div className="pr-1 text-right text-[11px] leading-6 text-muted">{MONTHS[months[i] - 1]}</div>
              {row.map((v, h) => {
                const t = v == null ? 0 : (v - lo) / (hi - lo || 1);
                return (
                  <div
                    key={h}
                    onMouseEnter={() => v != null && setHover({ m: months[i], h, v })}
                    onMouseLeave={() => setHover(null)}
                    className="h-6 rounded-[3px]"
                    style={{ background: v == null ? "var(--surface-2)" : `color-mix(in oklab, var(--s1) ${Math.round(8 + t * 92)}%, var(--surface))` }}
                    title={v == null ? "" : `${MONTHS[months[i] - 1]} ${h}:00 — ${num(v)} €/MWh`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-2">
        <div className="flex items-center gap-2">
          <span className="tabular">{num(lo, 0)} €</span>
          <span className="h-2 w-40 rounded-full" style={{ background: "linear-gradient(90deg, color-mix(in oklab, var(--s1) 8%, var(--surface)), var(--s1))" }} />
          <span className="tabular">{num(hi, 0)} €/MWh</span>
        </div>
        <span className="tabular">{hover ? `${MONTHS[hover.m - 1]} · ${String(hover.h).padStart(2, "0")}:00 → ${num(hover.v)} €/MWh` : "hover a cell"}</span>
      </div>
    </div>
  );
}

export default function Market() {
  const [days, setDays] = useState<"7" | "14" | "30">("14");
  const s = useMarketSummary();
  const prices = useMarketPrices(Number(days));
  const daily = useMarketDaily(365);
  const prof = useProfile();

  const px = useMemo(
    () =>
      (prices.data ?? []).map((r) => ({
        ...r,
        label: dayHourLabel(r.ts),
        load: r.load / 1000,
        solar: r.solar / 1000,
        wind: r.wind / 1000,
      })),
    [prices.data],
  );
  const monthly = useMemo(() => {
    const m = new Map<string, { month: string; neg: number; spread: number; n: number }>();
    for (const d of daily.data ?? []) {
      const k = d.date.slice(0, 7);
      const e = m.get(k) ?? { month: k, neg: 0, spread: 0, n: 0 };
      e.neg += d.neg_hours;
      e.spread += d.spread;
      e.n += 1;
      m.set(k, e);
    }
    return [...m.values()].map((e) => ({ ...e, spread: e.spread / e.n }));
  }, [daily.data]);

  const d = s.data;
  const PriceTip = makeTip<(typeof px)[number]>((r) => r.label, (r) => [{ name: "Day-ahead price", value: `${num(r.price)} €/MWh`, color: C.s1 }]);
  const FundTip = makeTip<(typeof px)[number]>(
    (r) => r.label,
    (r) => [
      { name: "Load", value: `${num(r.load)} GW`, color: C.ink },
      { name: "Wind", value: `${num(r.wind)} GW`, color: C.s1 },
      { name: "Solar", value: `${num(r.solar)} GW`, color: C.s4 },
    ],
  );
  const SpreadTip = makeTip<{ date: string; spread: number; mean: number }>(
    (r) => r.date,
    (r) => [
      { name: "Daily spread (max − min)", value: `${num(r.spread)} €/MWh`, color: C.s1 },
      { name: "Daily mean", value: `${num(r.mean)} €/MWh` },
    ],
  );
  const NegTip = makeTip<{ month: string; neg: number }>((r) => r.month, (r) => [{ name: "Negative-price hours", value: r.neg, color: C.s1, kind: "bar" }]);

  return (
    <>
      <PageHeader
        title="Market intelligence"
        subtitle="German–Luxembourg day-ahead zone: scraped prices and fundamentals. The arbitrage value of a battery is created by the daily spread — solar pushes midday prices down, evening ramps push them up."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Average price · last 30 days"
          value={`${num(d?.mean_30d)} €`}
          delta={d ? `${signedPct(d.mean_30d / d.mean_prev_30d - 1)} vs prior 30 d` : undefined}
          deltaGood={false}
          sub="€/MWh"
        />
        <Stat
          label="Average daily spread · 30 d"
          value={`${num(d?.avg_daily_spread_30d, 0)} €`}
          delta={d ? `${signedPct(d.avg_daily_spread_30d / d.avg_daily_spread_prev_30d - 1)} vs prior 30 d` : undefined}
          deltaGood={!!d && d.avg_daily_spread_30d >= d.avg_daily_spread_prev_30d}
          sub="the battery's raw material"
        />
        <Stat label="Negative-price hours · year to date" value={int(d?.neg_hours_ytd)} sub={`${int(d?.neg_hours_30d)} in the last 30 days`} />
        <Stat label="Renewable share of load · 30 d" value={`${num(d?.renewable_share_30d, 0)} %`} sub="wind + solar / load" />
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <ChartCard
          title="Day-ahead price"
          subtitle="Hourly, €/MWh (local time)"
          right={<Segmented value={days} onChange={setDays} options={[{ value: "7", label: "7 d" }, { value: "14", label: "14 d" }, { value: "30", label: "30 d" }]} />}
          loading={prices.isLoading}
          error={prices.error}
          table={{ columns: ["Hour", "€/MWh"], rows: px.map((r) => [r.label, num(r.price)]) }}
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={px} syncId="mkt" margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} minTickGap={60} />
              <YAxis {...AXIS} width={44} />
              <ReferenceLine y={0} stroke="var(--axis)" />
              <Tooltip content={<PriceTip />} cursor={CURSOR} />
              <Line dataKey="price" stroke={C.s1} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="Load, wind and solar"
          subtitle="GW — residual load (load − wind − solar) is what sets the price"
          legend={<Legend items={[{ label: "Load", color: C.ink }, { label: "Wind", color: C.s1 }, { label: "Solar", color: C.s4 }]} />}
          loading={prices.isLoading}
          error={prices.error}
          table={{ columns: ["Hour", "Load GW", "Wind GW", "Solar GW"], rows: px.map((r) => [r.label, num(r.load), num(r.wind), num(r.solar)]) }}
        >
          <ResponsiveContainer width="100%" height={236}>
            <LineChart data={px} syncId="mkt" margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} minTickGap={60} />
              <YAxis {...AXIS} width={44} />
              <Tooltip content={<FundTip />} cursor={CURSOR} />
              <Line dataKey="load" stroke={C.ink} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="wind" stroke={C.s1} strokeWidth={1.5} dot={false} isAnimationActive={false} />
              <Line dataKey="solar" stroke={C.s4} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-5">
        <ChartCard
          className="xl:col-span-3"
          title={`Average price by month and hour · ${prof.data?.year ?? ""}`}
          subtitle="The ‘duck curve’: solar hollows out midday prices, the evening peak carries the value"
          loading={prof.isLoading}
          error={prof.error}
          table={{
            columns: ["Month", ...Array.from({ length: 24 }, (_, h) => `${h}h`)],
            rows: (prof.data?.matrix ?? []).map((r, i) => [MONTHS[(prof.data?.months[i] ?? 1) - 1], ...r.map((v) => num(v, 0))]),
          }}
        >
          {prof.data && <Heatmap months={prof.data.months} matrix={prof.data.matrix} />}
        </ChartCard>
        <ChartCard
          className="xl:col-span-2"
          title="Negative-price hours per month"
          subtitle="Hours where producers pay to deliver — a battery gets paid to charge"
          loading={daily.isLoading}
          error={daily.error}
          table={{ columns: ["Month", "Negative hours"], rows: monthly.map((m) => [m.month, m.neg]) }}
        >
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={monthly} margin={{ top: 6, right: 8, bottom: 0, left: 0 }} barCategoryGap={3}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="month" {...AXIS} tickFormatter={(m: string) => MONTHS[Number(m.slice(5)) - 1]} minTickGap={8} />
              <YAxis {...AXIS} width={36} allowDecimals={false} />
              <Tooltip content={<NegTip />} cursor={{ fill: "var(--surface-2)" }} />
              <Bar dataKey="neg" fill={C.s1} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-3">
        <ChartCard
          title="Daily price spread · last 365 days"
          subtitle="max − min of the 24 hourly prices, €/MWh"
          loading={daily.isLoading}
          error={daily.error}
          table={{ columns: ["Date", "Spread", "Mean", "Neg. hours"], rows: (daily.data ?? []).map((r) => [r.date, num(r.spread), num(r.mean), r.neg_hours]) }}
        >
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={daily.data ?? []} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="date" {...AXIS} tickFormatter={dayLabel} minTickGap={50} />
              <YAxis {...AXIS} width={44} />
              <Tooltip content={<SpreadTip />} cursor={CURSOR} />
              <Area dataKey="spread" stroke={C.s1} strokeWidth={1.5} fill={C.s1} fillOpacity={0.1} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </>
  );
}
