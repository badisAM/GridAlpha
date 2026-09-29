"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ComposedChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { C } from "@/lib/colors";
import { eur, featureLabel, num } from "@/lib/format";
import { AXIS, CURSOR, GRID, makeTip } from "./primitives";

// ------------------------------------------------ SHAP drivers (diverging bars)
export function DriverBars({ drivers }: { drivers: { feature: string; impact_eur_mwh: number }[] }) {
  const data = drivers.map((d) => ({ name: featureLabel(d.feature), v: d.impact_eur_mwh }));
  const Tip = makeTip<{ name: string; v: number }>(
    (d) => d.name,
    (d) => [{ name: d.v >= 0 ? "Pushes price up" : "Pushes price down", value: `${d.v > 0 ? "+" : ""}${num(d.v)} €/MWh`, color: d.v >= 0 ? C.divPos : C.divNeg, kind: "bar" }],
  );
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 44, bottom: 0, left: 40 }} barCategoryGap={6}>
        <CartesianGrid stroke="var(--grid)" horizontal={false} />
        <XAxis type="number" {...AXIS} />
        <YAxis type="category" dataKey="name" {...AXIS} width={150} />
        <ReferenceLine x={0} stroke="var(--axis)" />
        <Tooltip content={<Tip />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar dataKey="v" maxBarSize={18} radius={4} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.v >= 0 ? C.divPos : C.divNeg} />
          ))}
          <LabelList dataKey="v" content={SignedLabel} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// value label placed beyond the bar end, on the side the bar grows to
function SignedLabel(props: { x?: number | string; y?: number | string; width?: number | string; height?: number | string; value?: unknown }) {
  const x = Number(props.x ?? 0), y = Number(props.y ?? 0), w = Number(props.width ?? 0), h = Number(props.height ?? 0);
  const v = Number(props.value);
  const neg = v < 0;
  const left = Math.min(x, x + w);
  const right = Math.max(x, x + w);
  const text = `${v > 0 ? "+" : ""}${num(v)}`;
  const inside = Math.abs(w) > 52; // long bar: label inside, near its end, in white
  const tx = inside ? (neg ? left + 6 : right - 6) : neg ? left - 6 : right + 6;
  const anchor = inside ? (neg ? "start" : "end") : neg ? "end" : "start";
  return (
    <text x={tx} y={y + h / 2} dy={4} textAnchor={anchor} fontSize={11} fill={inside ? "#ffffff" : "var(--ink-2)"} fontWeight={inside ? 600 : 400}>
      {text}
    </text>
  );
}

// ------------------------------------------------ risk frontier
export function FrontierChart({
  points,
  current,
}: {
  points: { risk_aversion: number; expected_pnl: number; cvar: number }[];
  current?: number;
}) {
  const Tip = makeTip<{ risk_aversion: number; expected_pnl: number; cvar: number }>(
    (d) => `Risk aversion λ = ${d.risk_aversion}`,
    (d) => [
      { name: "Expected P&L", value: eur(d.expected_pnl), color: C.s1 },
      { name: "CVaR 95 % (worst 5 %)", value: eur(d.cvar) },
    ],
  );
  return (
    <ResponsiveContainer width="100%" height={220}>
      <ComposedChart data={points} margin={{ top: 10, right: 16, bottom: 18, left: 0 }}>
        <CartesianGrid stroke="var(--grid)" />
        <XAxis type="number" dataKey="cvar" {...AXIS} domain={["auto", "auto"]} name="CVaR" tickFormatter={(v) => `${Math.round(v)}`}
          label={{ value: "CVaR 95 % of daily P&L (€) → safer", position: "insideBottom", offset: -10, fill: "var(--muted)", fontSize: 11 }} />
        <YAxis type="number" dataKey="expected_pnl" {...AXIS} width={52} domain={["auto", "auto"]} tickFormatter={(v) => `${Math.round(v)}`} />
        <Tooltip content={<Tip />} cursor={CURSOR} />
        <Line dataKey="expected_pnl" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
        <Scatter dataKey="expected_pnl" isAnimationActive={false}>
          {points.map((p, i) => (
            <Cell key={i} fill={p.risk_aversion === current ? "var(--accent)" : C.s1} stroke="var(--surface)" strokeWidth={2} r={p.risk_aversion === current ? 7 : 5} />
          ))}
          <LabelList
            dataKey="risk_aversion"
            position="top"
            formatter={(v: unknown) => {
              const n = Number(v);
              const last = points.length ? points[points.length - 1].risk_aversion : -1;
              return n === 0 || n === last || n === current ? `λ ${n}` : "";
            }}
            style={{ fill: "var(--muted)", fontSize: 10 }}
          />
        </Scatter>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------ scenario P&L histogram
export function PnlHistogram({ bins, expected, cvar }: { bins: { lo: number; hi: number; count: number }[]; expected?: number; cvar?: number }) {
  const data = bins.map((b) => ({ ...b, mid: (b.lo + b.hi) / 2 }));
  const Tip = makeTip<{ lo: number; hi: number; count: number }>(
    (d) => `${eur(d.lo)} – ${eur(d.hi)}`,
    (d) => [{ name: "Scenarios", value: d.count, color: C.s1, kind: "bar" }],
  );
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: 0 }} barCategoryGap={2}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="mid" {...AXIS} tickFormatter={(v) => `${Math.round(v)}`} minTickGap={24} />
        <YAxis {...AXIS} width={30} allowDecimals={false} />
        <Tooltip content={<Tip />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar dataKey="count" fill={C.s1} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
        {cvar != null && <ReferenceLine x={nearest(data, cvar)} stroke="var(--critical)" label={{ value: "CVaR", fill: "var(--ink-2)", fontSize: 10, position: "top" }} />}
        {expected != null && <ReferenceLine x={nearest(data, expected)} stroke="var(--ink)" label={{ value: "E[P&L]", fill: "var(--ink-2)", fontSize: 10, position: "top" }} />}
      </BarChart>
    </ResponsiveContainer>
  );
}

function nearest(data: { mid: number }[], v: number) {
  if (!data.length) return v;
  return data.reduce((a, b) => (Math.abs(b.mid - v) < Math.abs(a.mid - v) ? b : a)).mid;
}

// ------------------------------------------------ generic single-series horizontal bars
export function HBars({ data, unit = "", height, format }: { data: { name: string; v: number }[]; unit?: string; height?: number; format?: (v: number) => string }) {
  const f = format ?? ((v: number) => `${num(v)}${unit}`);
  const Tip = makeTip<{ name: string; v: number }>((d) => d.name, (d) => [{ name: "Value", value: f(d.v), color: C.s1, kind: "bar" }]);
  return (
    <ResponsiveContainer width="100%" height={height ?? Math.max(140, data.length * 30)}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 56, bottom: 0, left: 8 }} barCategoryGap={5}>
        <CartesianGrid stroke="var(--grid)" horizontal={false} />
        <XAxis type="number" {...AXIS} />
        <YAxis type="category" dataKey="name" {...AXIS} width={150} />
        <Tooltip content={<Tip />} cursor={{ fill: "var(--surface-2)" }} />
        <Bar dataKey="v" fill={C.s1} maxBarSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          <LabelList dataKey="v" position="right" formatter={(v: unknown) => f(Number(v))} style={{ fill: "var(--ink-2)", fontSize: 11 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ------------------------------------------------ sparkline
export function Spark({ data, k }: { data: Record<string, number>[]; k: string }) {
  return (
    <ResponsiveContainer width="100%" height={36}>
      <LineChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <Line dataKey={k} stroke={C.s1} strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
