"use client";

import clsx from "clsx";
import { Pause, Play, Radio } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS, CURSOR, GRID, makeTip } from "@/components/charts/primitives";
import { Card, ChartCard, Legend, PageHeader, Segmented } from "@/components/ui";
import { wsUrl, type Tick } from "@/lib/api";
import { C, SERIES } from "@/lib/colors";
import { eur, num } from "@/lib/format";

type Speed = "2" | "5" | "12";

export default function Live() {
  const [ticks, setTicks] = useState<(Tick & { band: [number, number] | null })[]>([]);
  const [status, setStatus] = useState<"connecting" | "open" | "closed">("connecting");
  const [paused, setPaused] = useState(false);
  const [speed, setSpeed] = useState<Speed>("5");
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout>;
    let closed = false;
    const connect = () => {
      setStatus("connecting");
      ws = new WebSocket(wsUrl(`/ws/replay?speed=${speed}`));
      ws.onopen = () => setStatus("open");
      ws.onclose = () => {
        setStatus("closed");
        if (!closed) retry = setTimeout(connect, 3000);
      };
      ws.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.type !== "tick" || pausedRef.current) return;
        const t = m as Tick;
        setTicks((prev) => {
          const next = t.i === 0 ? [] : prev;
          return [...next.slice(-71), { ...t, band: t.q10 != null && t.q90 != null ? [t.q10, t.q90] : null }];
        });
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      ws?.close();
    };
  }, [speed]);

  const last = ticks[ticks.length - 1];
  const edge = last && last.pnl_naive != null ? last.pnl_ai - last.pnl_naive : null;
  const Tip = makeTip<Tick>(
    (d) => d.local,
    (d) => [
      { name: "Cleared price", value: `${num(d.price)} €/MWh`, color: C.ink },
      { name: "AI forecast P50", value: `${num(d.q50)} €/MWh`, color: C.s1 },
      { name: "Action", value: d.action === "IDLE" ? "idle" : `${d.action.toLowerCase()} ${num(d.mw, 1)} MW` },
      { name: "State of charge", value: `${num(d.soc, 1)} MWh` },
    ],
  );

  return (
    <>
      <PageHeader
        title="Live desk replay"
        subtitle="WebSocket stream replaying the last settled week hour by hour: what the battery did, at which price, and the running P&L of the AI strategy vs the naive desk. (Replay of settled history — not an exchange feed.)"
        right={
          <div className="flex items-center gap-2">
            <span className={clsx("inline-flex items-center gap-1.5 text-xs", status === "open" ? "text-good-text" : "text-ink-2")}>
              <Radio size={13} className={status === "open" && !paused ? "animate-pulse" : ""} /> {status}
            </span>
            <Segmented value={speed} onChange={setSpeed} options={[{ value: "2", label: "2×" }, { value: "5", label: "5×" }, { value: "12", label: "12×" }]} />
            <button onClick={() => setPaused((p) => !p)} className="inline-flex h-7 items-center gap-1 rounded-md border border-line px-2 text-xs hover:bg-surface-2">
              {paused ? <Play size={13} /> : <Pause size={13} />} {paused ? "Resume" : "Pause"}
            </button>
          </div>
        }
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Card className="p-4">
          <div className="text-xs text-ink-2">Delivery hour</div>
          <div className="mt-1.5 text-lg font-semibold">{last?.local ?? "—"}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-ink-2">Cleared price</div>
          <div className="mt-1.5 text-2xl font-semibold">{num(last?.price)} €</div>
          <div className="text-xs text-muted">forecast {num(last?.q50)} €</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-ink-2">Battery action</div>
          <div className="mt-1.5 flex items-center gap-2 text-2xl font-semibold">
            <span className="size-2.5 rounded-full" style={{ background: last?.action === "CHARGE" ? C.charge : last?.action === "DISCHARGE" ? C.discharge : "var(--axis)" }} />
            {last ? (last.action === "IDLE" ? "Idle" : last.action === "CHARGE" ? "Charging" : "Discharging") : "—"}
          </div>
          <div className="text-xs text-muted">{last && last.action !== "IDLE" ? `${num(last.mw, 1)} MW · SoC ${num(last.soc, 1)} MWh` : `SoC ${num(last?.soc, 1)} MWh`}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-ink-2">AI strategy · week to date</div>
          <div className="mt-1.5 text-2xl font-semibold">{eur(last?.pnl_ai)}</div>
          <div className="text-xs text-muted">naive desk {eur(last?.pnl_naive)}</div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-ink-2">AI edge vs naive</div>
          <div className={clsx("mt-1.5 text-2xl font-semibold", edge != null && edge >= 0 && "text-good-text")}>{edge == null ? "—" : `${edge >= 0 ? "+" : ""}${eur(edge)}`}</div>
          <div className="text-xs text-muted">same battery, same hours</div>
        </Card>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <ChartCard
          className="xl:col-span-2"
          title="Price tape"
          subtitle="Last 72 streamed hours"
          legend={<Legend items={[{ label: "Cleared price", color: C.ink }, { label: "AI forecast P50", color: C.s1 }, { label: "P10–P90", color: C.s1, kind: "band" }]} />}
        >
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={ticks} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="local" {...AXIS} minTickGap={70} />
              <YAxis {...AXIS} width={44} />
              <ReferenceLine y={0} stroke="var(--axis)" />
              <Tooltip content={<Tip />} cursor={CURSOR} />
              <Area dataKey="band" stroke="none" fill={C.s1} fillOpacity={0.14} isAnimationActive={false} />
              <Line dataKey="q50" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="price" stroke={C.ink} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-3 text-[11px] font-medium text-muted">Cumulative P&L · €</div>
          <ResponsiveContainer width="100%" height={150}>
            <ComposedChart data={ticks} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="local" {...AXIS} minTickGap={70} />
              <YAxis {...AXIS} width={56} />
              <Tooltip cursor={CURSOR} content={() => null} />
              <Line dataKey="pnl_ai" stroke={SERIES.ensemble_cvar} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Line dataKey="pnl_naive" stroke={SERIES.naive_d1} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
          <Legend items={[{ label: "AI ensemble + CVaR", color: SERIES.ensemble_cvar }, { label: "Naive D-1", color: SERIES.naive_d1 }]} />
        </ChartCard>
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">Order log</h2>
          <ul className="max-h-[520px] space-y-1 overflow-auto font-mono text-xs">
            {[...ticks]
              .reverse()
              .filter((t) => t.action !== "IDLE")
              .slice(0, 40)
              .map((t) => (
                <li key={t.ts} className="flex items-center justify-between gap-2 rounded px-2 py-1 hover:bg-surface-2">
                  <span className="text-muted">{t.local}</span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="size-2 rounded-full" style={{ background: t.action === "CHARGE" ? C.charge : C.discharge }} />
                    {t.action === "CHARGE" ? "BUY " : "SELL"} {num(t.mw, 1)} MW
                  </span>
                  <span className="tabular">@ {num(t.price)} €</span>
                </li>
              ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
