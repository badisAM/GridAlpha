"use client";

import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { C, SERIES } from "@/lib/colors";
import { MODEL_LABEL, num } from "@/lib/format";
import { AXIS, CURSOR, GRID, makeTip } from "./primitives";

export type PanelRow = {
  label: string;
  q10: number;
  q50: number;
  q90: number;
  band: [number, number];
  actual?: number | null;
  charge: number; // MW, shown negative
  discharge: number;
  soc: number;
  compare?: number | null;
};

type Props = {
  rows: PanelRow[];
  energyMwh: number;
  compareKey?: string | null;
  syncId?: string;
  height?: number;
};

/**
 * Three aligned small multiples sharing the hour axis (never a dual axis):
 *   price forecast fan (€/MWh) · battery power (MW) · state of charge (MWh)
 */
export default function DispatchPanels({ rows, energyMwh, compareKey, syncId = "desk", height = 250 }: Props) {
  const PriceTip = makeTip<PanelRow>(
    (d) => `${d.label} (Europe/Berlin)`,
    (d) => [
      { name: "AI forecast P50", value: `${num(d.q50)} €`, color: C.s1 },
      { name: "P10 – P90", value: `${num(d.q10, 0)} – ${num(d.q90, 0)} €`, color: C.s1, kind: "band" },
      ...(d.actual != null ? [{ name: "Realised price", value: `${num(d.actual)} €`, color: C.ink }] : []),
      ...(compareKey && d.compare != null
        ? [{ name: MODEL_LABEL[compareKey] ?? compareKey, value: `${num(d.compare)} €`, color: SERIES[compareKey] }]
        : []),
    ],
  );
  const PowerTip = makeTip<PanelRow>(
    (d) => d.label,
    (d) => [
      { name: "Discharge (sell)", value: `${num(d.discharge, 2)} MW`, color: C.discharge, kind: "bar" },
      { name: "Charge (buy)", value: `${num(d.charge, 2)} MW`, color: C.charge, kind: "bar" },
    ],
  );
  const SocTip = makeTip<PanelRow>(
    (d) => d.label,
    (d) => [{ name: "State of charge", value: `${num(d.soc, 1)} MWh (${num((d.soc / energyMwh) * 100, 0)} %)`, color: C.s1 }],
  );
  const data = rows.map((r) => ({ ...r, chargeNeg: -r.charge }));

  return (
    <div className="space-y-1">
      <div className="text-[11px] font-medium text-muted">Price · €/MWh</div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} syncId={syncId} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} interval={2} hide />
          <YAxis {...AXIS} width={44} />
          <ReferenceLine y={0} stroke="var(--axis)" />
          <Tooltip content={<PriceTip />} cursor={CURSOR} />
          <Area dataKey="band" stroke="none" fill={C.s1} fillOpacity={0.14} isAnimationActive={false} />
          {compareKey && (
            <Line dataKey="compare" stroke={SERIES[compareKey]} strokeWidth={1.5} dot={false} isAnimationActive={false} />
          )}
          <Line dataKey="q50" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line dataKey="actual" stroke={C.ink} strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="pt-2 text-[11px] font-medium text-muted">Battery power · MW (+ sell / − buy)</div>
      <ResponsiveContainer width="100%" height={130}>
        <ComposedChart data={data} syncId={syncId} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap={3}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} interval={2} hide />
          <YAxis {...AXIS} width={44} />
          <ReferenceLine y={0} stroke="var(--axis)" />
          <Tooltip content={<PowerTip />} cursor={{ fill: "var(--surface-2)" }} />
          <Bar dataKey="discharge" stackId="p" fill={C.discharge} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          <Bar dataKey="chargeNeg" stackId="p" fill={C.charge} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>

      <div className="pt-2 text-[11px] font-medium text-muted">State of charge · MWh</div>
      <ResponsiveContainer width="100%" height={110}>
        <ComposedChart data={data} syncId={syncId} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          <XAxis dataKey="label" {...AXIS} interval={2} />
          <YAxis {...AXIS} width={44} domain={[0, energyMwh]} />
          <Tooltip content={<SocTip />} cursor={CURSOR} />
          <Area dataKey="soc" type="monotone" stroke={C.s1} strokeWidth={2} fill={C.s1} fillOpacity={0.1} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
