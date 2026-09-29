"use client";

import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS, CURSOR, GRID, makeTip } from "@/components/charts/primitives";
import { Card, ChartCard, DataTable, PageHeader, Stat, StatusPill } from "@/components/ui";
import { C } from "@/lib/colors";
import { ago, dayLabel, featureLabel, int, num, pct } from "@/lib/format";
import { useDataQuality, useDrift, useHealth, useLatency, usePipelineRuns } from "@/lib/hooks";

const STEP_ORDER = ["ingest", "features", "backtest", "train_challenger", "train_champion", "forecast", "optimise", "monitoring", "copilot"];

function StepBar({ steps }: { steps: Record<string, number> }) {
  const total = Object.values(steps).reduce((a, b) => a + b, 0) || 1;
  const keys = STEP_ORDER.filter((k) => steps[k] != null);
  const palette = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)"];
  return (
    <div className="flex h-2.5 w-48 gap-[2px] overflow-hidden rounded-full" title={keys.map((k) => `${k} ${num(steps[k], 1)} s`).join(" · ")}>
      {keys.map((k, i) => (
        <div key={k} style={{ width: `${(steps[k] / total) * 100}%`, background: palette[i % palette.length], minWidth: 2 }} />
      ))}
    </div>
  );
}

export default function Monitoring() {
  const health = useHealth();
  const runs = usePipelineRuns(!!health.data?.pipeline_running);
  const dq = useDataQuality();
  const drift = useDrift();
  const lat = useLatency();
  const perf = drift.data?.performance;
  const last = runs.data?.[0];

  const PerfTip = makeTip<{ date: string; mae: number; coverage: number }>(
    (d) => d.date,
    (d) => [
      { name: "7-day MAE", value: `${num(d.mae, 2)} €/MWh`, color: C.s1 },
      { name: "7-day coverage", value: pct(d.coverage) },
    ],
  );
  const CovTip = makeTip<{ date: string; coverage: number }>((d) => d.date, (d) => [{ name: "P10–P90 coverage (7 d)", value: pct(d.coverage), color: C.s1 }]);

  return (
    <>
      <PageHeader
        title="Monitoring"
        subtitle="MLOps view: pipeline runs, data-quality gate, feature drift, forecast degradation and live API latency (refreshes every 5 s)."
      />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Last pipeline run" value={last ? <StatusPill status={last.status} /> : "—"} sub={last ? `${ago(last.finished_at)} · ${num(last.duration_s, 0)} s · ${last.data_mode ?? ""}` : "never"} />
        <Stat label="Data-quality gate" value={dq.data ? <StatusPill status={dq.data.status} /> : "—"} sub={dq.data ? `${int(dq.data.rows)} hourly rows · ${dq.data.mode} mode` : undefined} />
        <Stat label="Forecast health (7 d)" value={perf ? <StatusPill status={perf.status} /> : "—"} sub={perf ? `MAE ${num(perf.recent_mae, 1)} vs ${num(perf.overall_mae, 1)} €/MWh overall` : undefined} />
        <Stat label="API latency p95" value={lat.data?.p95_ms != null ? `${num(lat.data.p95_ms, 1)} ms` : "—"} sub={lat.data ? `p50 ${num(lat.data.p50_ms, 1)} ms · ${int(lat.data.count)} requests` : undefined} />
      </div>

      <Card className="mt-3 p-4">
        <h2 className="mb-3 text-sm font-semibold">Pipeline runs</h2>
        <DataTable
          columns={["Run", "Started", "Status", "Mode", "Target day", "Duration", "Steps (ingest → report)"]}
          align={["left", "left", "left", "left", "left", "right", "left"]}
          rows={(runs.data ?? []).slice(0, 10).map((r) => [
            <span key="id" className="font-mono text-xs">{r.run_id}</span>,
            r.started_at.slice(0, 19).replace("T", " "),
            <StatusPill key="s" status={r.status} />,
            r.data_mode ?? "—",
            r.target_day ?? "—",
            r.duration_s != null ? `${num(r.duration_s, 0)} s` : "—",
            r.error ? <span key="e" className="text-xs text-critical">{r.error.slice(0, 80)}</span> : <StepBar key="b" steps={r.steps} />,
          ])}
        />
      </Card>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <Card className="p-4">
          <h2 className="text-sm font-semibold">Data quality & sources</h2>
          <p className="mt-0.5 mb-3 text-xs text-ink-2">
            Fetched {ago(dq.data?.fetched_at)} · requested mode <b>{dq.data?.requested_mode}</b> → running <b>{dq.data?.mode}</b>
            {dq.data?.fallback_reason && <> · fallback reason: <span className="font-mono">{dq.data.fallback_reason.slice(0, 90)}</span></>}
          </p>
          <div className="mb-3 flex flex-wrap gap-2">
            {Object.entries(dq.data?.sources ?? {}).map(([k, v]) => (
              <StatusPill key={k} status={v === "ok" ? "ok" : "warn"} label={`${k}: ${v.slice(0, 40)}`} />
            ))}
          </div>
          <DataTable
            columns={["Series", "Coverage", "Out of range", "Max gap / stale", "Status"]}
            rows={(dq.data?.checks ?? []).map((c) => [
              c.column + (c.optional ? " (opt.)" : ""),
              pct(c.coverage, 1),
              c.out_of_range,
              `${c.longest_gap_h} h / ${c.staleness_h == null ? "—" : `${num(c.staleness_h, 0)} h`}`,
              <StatusPill key="s" status={c.status} />,
            ])}
          />
        </Card>
        <Card className="p-4">
          <h2 className="text-sm font-semibold">Feature drift</h2>
          <p className="mt-0.5 mb-3 text-xs text-ink-2">
            Last 28 days vs the same calendar window in previous years (PSI: &lt; 0.1 stable, &lt; 0.25 moderate). Level variables (gas, price) use the
            out-of-training-range share instead — trees cannot extrapolate. Drift is informative; retraining is triggered by forecast degradation.
          </p>
          <DataTable
            columns={["Feature", "Metric", "Value", "Mean: ref → now", "Status"]}
            rows={(drift.data?.data ?? []).map((d) => [
              featureLabel(d.feature),
              d.metric === "psi" ? "PSI" : "OOD",
              d.value == null ? "—" : d.metric === "psi" ? num(d.value, 3) : pct(d.value),
              `${num(d.ref_mean, 1)} → ${num(d.cur_mean, 1)}`,
              <StatusPill key="s" status={d.status} />,
            ])}
          />
        </Card>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <ChartCard
          title="Forecast error · rolling 7 days"
          subtitle={perf ? `MAE €/MWh — backtest average ${num(perf.overall_mae, 2)} (reference line); retrain if > 1.6×` : undefined}
          loading={drift.isLoading}
          error={drift.error}
          table={{ columns: ["Date", "MAE", "Coverage"], rows: (perf?.series ?? []).map((r) => [r.date, num(r.mae, 2), pct(r.coverage)]) }}
        >
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={perf?.series ?? []} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="date" {...AXIS} tickFormatter={dayLabel} minTickGap={40} />
              <YAxis {...AXIS} width={36} />
              <Tooltip content={<PerfTip />} cursor={CURSOR} />
              {perf && <ReferenceLine y={perf.overall_mae} stroke="var(--ref)" />}
              <Line dataKey="mae" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="Interval coverage · rolling 7 days"
          subtitle="Share of realised prices inside the P10–P90 band (target 80 %, shaded 75–85 %)"
          loading={drift.isLoading}
          error={drift.error}
          table={{ columns: ["Date", "Coverage"], rows: (perf?.series ?? []).map((r) => [r.date, pct(r.coverage)]) }}
        >
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={perf?.series ?? []} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="date" {...AXIS} tickFormatter={dayLabel} minTickGap={40} />
              <YAxis {...AXIS} width={40} domain={[0.5, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
              <ReferenceArea y1={0.75} y2={0.85} fill="var(--good)" fillOpacity={0.08} />
              <Tooltip content={<CovTip />} cursor={CURSOR} />
              <Line dataKey="coverage" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <Card className="mt-3 p-4">
        <h2 className="mb-1 text-sm font-semibold">API latency by route</h2>
        <p className="mb-3 text-xs text-ink-2">Measured server-side by an ASGI middleware (also exposed as a Server-Timing header). Responses are cached against the lake snapshot, so reads are memory-speed until the next pipeline run.</p>
        <DataTable
          columns={["Route", "Requests", "p50", "p95", "p99"]}
          rows={(lat.data?.routes ?? []).map((r) => [<span key="r" className="font-mono text-xs">{r.route}</span>, r.count, `${num(r.p50_ms, 1)} ms`, `${num(r.p95_ms, 1)} ms`, `${num(r.p99_ms, 1)} ms`])}
          maxHeight={360}
        />
      </Card>
    </>
  );
}
