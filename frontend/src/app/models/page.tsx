"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { HBars } from "@/components/charts/Small";
import { AXIS, CURSOR, GRID, TipBox, makeTip } from "@/components/charts/primitives";
import { Card, ChartCard, DataTable, Legend, PageHeader, StatusPill } from "@/components/ui";
import { C, SERIES } from "@/lib/colors";
import { dayLabel, eur, featureLabel, MODEL_LABEL, num, pct } from "@/lib/format";
import { useCalibration, useErrorByHour, useExplain, useLeaderboard, useRegistry, useWeights } from "@/lib/hooks";

const LINES = ["ensemble", "lgbm", "tide", "profile7", "naive_d1"];

function MultiTip(props: { active?: boolean; label?: string | number; payload?: readonly { dataKey?: unknown; value?: unknown }[] }) {
  if (!props.active || !props.payload?.length) return null;
  return (
    <TipBox
      title={`${props.label}:00`}
      rows={props.payload.map((p) => ({
        name: MODEL_LABEL[String(p.dataKey)] ?? String(p.dataKey),
        value: `${num(Number(p.value))} €/MWh`,
        color: SERIES[String(p.dataKey)],
      }))}
    />
  );
}

export default function Models() {
  const lb = useLeaderboard();
  const eh = useErrorByHour();
  const cal = useCalibration();
  const ex = useExplain();
  const w = useWeights();
  const reg = useRegistry();

  const calData = useMemo(() => {
    const pts: Record<string, number>[] = [0.1, 0.5, 0.9].map((n) => ({ nominal: n * 100, ideal: n * 100 }));
    for (const m of cal.data ?? []) {
      m.points.forEach((p, i) => (pts[i][m.model] = p.empirical * 100));
    }
    return pts;
  }, [cal.data]);
  const wData: Record<string, number | string>[] = useMemo(
    () => (w.data ?? []).map((r) => ({ ...r, label: dayLabel(String(r.delivery_date)) })),
    [w.data],
  );
  const card = reg.data?.champion_card as Record<string, unknown> | undefined;
  const hist = (card?.tide_history as { seed: number; epochs: number; warm_start: boolean; val_pinball_norm: number }[] | undefined) ?? [];

  const CalTip = makeTip<Record<string, number>>(
    (d) => `Nominal quantile ${d.nominal} %`,
    (d) => LINES.filter((m) => d[m] != null).map((m) => ({ name: MODEL_LABEL[m], value: `${num(d[m])} %`, color: SERIES[m] })),
  );
  const WTip = makeTip<Record<string, number | string>>(
    (d) => String(d.delivery_date),
    (d) => [
      { name: "LightGBM weight", value: pct(Number(d.w_lgbm)), color: SERIES.lgbm },
      ...(d.w_tide != null ? [{ name: "TiDE weight", value: pct(Number(d.w_tide)), color: SERIES.tide }] : []),
      { name: "Conformal scale", value: `× ${num(Number(d.conformal_scale), 2)}` },
    ],
  );

  return (
    <>
      <PageHeader
        title="Models"
        subtitle="Five forecasters compete on the same walk-forward protocol. The online ensemble re-weights experts daily from their recent pinball loss; adaptive conformal calibration keeps the 80 % band honest."
      />
      <Card className="p-4">
        <h2 className="mb-1 text-sm font-semibold">Leaderboard · walk-forward out-of-sample</h2>
        <p className="mb-3 text-xs text-ink-2">
          Kendall τ and peak-hour hit rate measure what a battery monetises: ranking the hours correctly. Lower is better for MAE/RMSE/pinball.
        </p>
        <DataTable
          columns={["Model", "MAE", "RMSE", "Pinball", "Coverage 80 %", "Band width", "Kendall τ", "Peak hit", "Trough hit", "Capture", "€/MW/yr"]}
          rows={(lb.data ?? []).map((r) => [
            <span key={r.model} className="inline-flex items-center gap-2">
              <span className="h-0.5 w-3 rounded-full" style={{ background: SERIES[r.model] }} />
              {MODEL_LABEL[r.model] ?? r.model}
            </span>,
            num(r.mae, 2),
            num(r.rmse, 2),
            num(r.pinball, 2),
            pct(r.coverage_80),
            num(r.interval_width, 1),
            num(r.kendall_tau, 3),
            pct(r.peak_hour_hit, 0),
            pct(r.trough_hour_hit, 0),
            pct(r.capture_ratio),
            eur(r.eur_per_mw_year),
          ])}
        />
      </Card>

      <div className="mt-3 grid gap-3 xl:grid-cols-2">
        <ChartCard
          title="Error by hour of day"
          subtitle="MAE, €/MWh — solar ramps and the evening peak are the hard hours"
          loading={eh.isLoading}
          error={eh.error}
          legend={<Legend items={LINES.map((k) => ({ label: MODEL_LABEL[k], color: SERIES[k] }))} />}
          table={{ columns: ["Hour", ...LINES.map((k) => MODEL_LABEL[k])], rows: (eh.data ?? []).map((r) => [r.hour, ...LINES.map((k) => num(r[k]))]) }}
        >
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={eh.data ?? []} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="hour" {...AXIS} />
              <YAxis {...AXIS} width={36} />
              <Tooltip content={<MultiTip />} cursor={CURSOR} />
              {LINES.map((k) => (
                <Line key={k} dataKey={k} stroke={SERIES[k]} strokeWidth={k === "ensemble" ? 2.5 : 1.5} dot={false} isAnimationActive={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          title="Calibration (reliability)"
          subtitle="Share of realised prices below each predicted quantile — on the diagonal = calibrated"
          loading={cal.isLoading}
          error={cal.error}
          legend={<Legend items={[{ label: "Ideal", color: C.ref }, ...LINES.map((k) => ({ label: MODEL_LABEL[k], color: SERIES[k] }))]} />}
          table={{ columns: ["Nominal %", ...LINES.map((k) => MODEL_LABEL[k])], rows: calData.map((r) => [r.nominal, ...LINES.map((k) => num(r[k]))]) }}
        >
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={calData} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis type="number" dataKey="nominal" domain={[0, 100]} ticks={[0, 10, 50, 90, 100]} {...AXIS} />
              <YAxis type="number" domain={[0, 100]} ticks={[0, 10, 50, 90, 100]} {...AXIS} width={36} />
              <Tooltip content={<CalTip />} cursor={CURSOR} />
              <Line dataKey="ideal" stroke={C.ref} strokeWidth={1} dot={false} isAnimationActive={false} />
              {LINES.map((k) => (
                <Line key={k} dataKey={k} stroke={SERIES[k]} strokeWidth={k === "ensemble" ? 2.5 : 1.5} isAnimationActive={false}
                  dot={{ r: 4, fill: SERIES[k], stroke: "var(--surface)", strokeWidth: 2 }} />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-3">
        <ChartCard
          title="Global feature importance"
          subtitle="Mean |TreeSHAP| share over the last 90 days (LightGBM median model)"
          loading={ex.isLoading}
          error={ex.error}
          table={{ columns: ["Feature", "Share %"], rows: (ex.data?.global_importance ?? []).map((g) => [featureLabel(g.feature), num(g.share_pct)]) }}
        >
          <HBars data={(ex.data?.global_importance ?? []).slice(0, 10).map((g) => ({ name: featureLabel(g.feature), v: g.share_pct }))} format={(v) => `${num(v, 1)} %`} />
        </ChartCard>
        <ChartCard
          className="xl:col-span-2"
          title="Online ensemble weights"
          subtitle="Softmax of each expert's 28-day relative pinball loss — shifts automatically when a model degrades"
          loading={w.isLoading}
          error={w.error}
          legend={<Legend items={[{ label: "LightGBM", color: SERIES.lgbm, kind: "band" }, { label: "TiDE", color: SERIES.tide, kind: "band" }]} />}
          table={{ columns: ["Date", "w LightGBM", "w TiDE", "Conformal ×"], rows: wData.map((r) => [String(r.delivery_date), pct(Number(r.w_lgbm)), pct(Number(r.w_tide ?? 0)), num(Number(r.conformal_scale), 2)]) }}
        >
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={wData} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} minTickGap={50} />
              <YAxis {...AXIS} width={36} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
              <Tooltip content={<WTip />} cursor={CURSOR} />
              <Area dataKey="w_lgbm" stackId="w" stroke={SERIES.lgbm} strokeWidth={1.5} fill={SERIES.lgbm} fillOpacity={0.12} isAnimationActive={false} />
              <Area dataKey="w_tide" stackId="w" stroke={SERIES.tide} strokeWidth={1.5} fill={SERIES.tide} fillOpacity={0.12} isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
          <div className="mt-3 text-[11px] font-medium text-muted">Adaptive-conformal band multiplier (1 = raw model quantiles)</div>
          <ResponsiveContainer width="100%" height={110}>
            <LineChart data={wData} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...GRID} />
              <XAxis dataKey="label" {...AXIS} minTickGap={50} />
              <YAxis {...AXIS} width={36} domain={["auto", "auto"]} />
              <Tooltip content={<WTip />} cursor={CURSOR} />
              <Line dataKey="conformal_scale" stroke={C.s1} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">Model registry</h2>
          <DataTable
            columns={["Version", "Data", "Train until", "Capture", "MAE", ""]}
            rows={(reg.data?.versions ?? []).map((v) => [
              <span key="v" className="font-mono text-xs">{String(v.version)}</span>,
              String(v.data_mode ?? ""),
              String(v.train_until ?? ""),
              pct(Number(v.capture_ratio)),
              num(Number(v.mae), 2),
              v.version === reg.data?.champion ? <StatusPill key="c" status="pass" label="Champion" /> : "",
            ])}
          />
          <p className="mt-3 text-xs text-muted">
            A new version is promoted to champion only if its backtest capture ratio is within 2 pts of the current champion (retrain guard-rail). Artefacts:
            LightGBM boosters (txt), TiDE weights (pt), model card (json). Optional MLflow logging via <code className="font-mono">MLFLOW_TRACKING_URI</code>.
          </p>
        </Card>
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold">Champion model card</h2>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-ink-2">Experts</dt>
            <dd>{((card?.models as string[]) ?? []).map((m) => MODEL_LABEL[m] ?? m).join(", ")}</dd>
            <dt className="text-ink-2">Ensemble weights</dt>
            <dd className="tabular">
              {Object.entries((card?.ensemble_weights as Record<string, number>) ?? {})
                .map(([k, v]) => `${MODEL_LABEL[k] ?? k} ${pct(v, 0)}`)
                .join(" · ")}
            </dd>
            <dt className="text-ink-2">Features</dt>
            <dd>{((card?.features as string[]) ?? []).length} engineered, leakage-tested</dd>
            <dt className="text-ink-2">Trained until</dt>
            <dd>{String(card?.train_until ?? "—")}</dd>
          </dl>
          {hist.length > 0 && (
            <>
              <h3 className="mt-4 mb-2 text-xs font-semibold text-ink-2">TiDE training (seed ensemble)</h3>
              <DataTable
                columns={["Seed", "Epochs", "Warm start", "Val. pinball (norm.)"]}
                rows={hist.map((h) => [h.seed, h.epochs, h.warm_start ? "yes" : "no", num(h.val_pinball_norm, 4)])}
              />
            </>
          )}
        </Card>
      </div>
    </>
  );
}
