"use client";

import clsx from "clsx";
import { AlertTriangle, CheckCircle2, CircleDashed, Info, OctagonAlert, Sparkles, Table2, TrendingUp } from "lucide-react";
import { useState, type ReactNode } from "react";

// ------------------------------------------------------------------ Card
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={clsx("rounded-xl border border-line bg-surface", className)}>{children}</section>;
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight md:text-2xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink-2">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

// ------------------------------------------------------------------ Stat tile
export function Stat({
  label,
  value,
  sub,
  delta,
  deltaGood,
  hint,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  delta?: string;
  deltaGood?: boolean;
  hint?: string;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-1 text-xs text-ink-2" title={hint}>
        {label}
      </div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight">{value}</div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
        {delta && (
          <span className={clsx("inline-flex items-center gap-0.5 font-medium", deltaGood ? "text-good-text" : "text-ink-2")}>
            <TrendingUp size={12} className={deltaGood ? "" : "rotate-180"} />
            {delta}
          </span>
        )}
        {sub}
      </div>
    </Card>
  );
}

export function Hero({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <Card className="flex flex-col justify-between p-5">
      <div className="text-sm text-ink-2">{label}</div>
      <div className="mt-2 text-5xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-2 text-xs text-ink-2">{sub}</div>}
    </Card>
  );
}

// ------------------------------------------------------------------ Status (icon + label, never colour alone)
const STATUS: Record<string, { cls: string; Icon: typeof CheckCircle2; label?: string }> = {
  pass: { cls: "text-good-text border-good/40", Icon: CheckCircle2, label: "Pass" },
  success: { cls: "text-good-text border-good/40", Icon: CheckCircle2, label: "Success" },
  healthy: { cls: "text-good-text border-good/40", Icon: CheckCircle2, label: "Healthy" },
  stable: { cls: "text-good-text border-good/40", Icon: CheckCircle2, label: "Stable" },
  ok: { cls: "text-good-text border-good/40", Icon: CheckCircle2, label: "OK" },
  warn: { cls: "text-ink border-warning/60", Icon: AlertTriangle, label: "Warn" },
  watch: { cls: "text-ink border-warning/60", Icon: AlertTriangle, label: "Watch" },
  moderate: { cls: "text-ink border-warning/60", Icon: AlertTriangle, label: "Moderate" },
  warning: { cls: "text-ink border-warning/60", Icon: AlertTriangle, label: "Warning" },
  miss: { cls: "text-ink border-serious/60", Icon: OctagonAlert, label: "Miss" },
  significant: { cls: "text-ink border-serious/60", Icon: OctagonAlert, label: "Significant" },
  fail: { cls: "text-critical border-critical/60", Icon: OctagonAlert, label: "Fail" },
  failed: { cls: "text-critical border-critical/60", Icon: OctagonAlert, label: "Failed" },
  degraded: { cls: "text-critical border-critical/60", Icon: OctagonAlert, label: "Degraded" },
  running: { cls: "text-ink-2 border-line", Icon: CircleDashed, label: "Running" },
  info: { cls: "text-ink-2 border-line", Icon: Info, label: "Info" },
  notice: { cls: "text-ink-2 border-line", Icon: Info, label: "Notice" },
  opportunity: { cls: "text-good-text border-good/40", Icon: Sparkles, label: "Opportunity" },
};

export function StatusPill({ status, label }: { status: string; label?: string }) {
  const s = STATUS[status] ?? { cls: "text-muted border-line", Icon: CircleDashed, label: status };
  return (
    <span className={clsx("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium", s.cls)}>
      <s.Icon size={12} />
      {label ?? s.label}
    </span>
  );
}

export function StatusIcon({ status }: { status: string }) {
  const s = STATUS[status] ?? STATUS.info;
  const color =
    s.cls.includes("good") ? "text-good" : s.cls.includes("warning") ? "text-warning" : s.cls.includes("serious") ? "text-serious" : s.cls.includes("critical") ? "text-critical" : "text-muted";
  return <s.Icon size={15} className={clsx("mt-0.5 shrink-0", color)} aria-label={s.label} />;
}

// ------------------------------------------------------------------ Legend (swatch + text in ink)
export function Legend({ items }: { items: { label: string; color: string; kind?: "line" | "band" | "bar" }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          {it.kind === "band" ? (
            <span className="h-2.5 w-4 rounded-sm" style={{ background: it.color, opacity: 0.25 }} />
          ) : it.kind === "bar" ? (
            <span className="size-2.5 rounded-sm" style={{ background: it.color }} />
          ) : (
            <span className="h-0.5 w-4 rounded-full" style={{ background: it.color }} />
          )}
          {it.label}
        </span>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ Chart frame with table view twin
export function ChartCard({
  title,
  subtitle,
  legend,
  children,
  table,
  right,
  className,
  loading,
  error,
}: {
  title: string;
  subtitle?: ReactNode;
  legend?: ReactNode;
  children: ReactNode;
  table?: { columns: string[]; rows: (string | number | null)[][] };
  right?: ReactNode;
  className?: string;
  loading?: boolean;
  error?: unknown;
}) {
  const [showTable, setShowTable] = useState(false);
  return (
    <Card className={clsx("flex flex-col p-4", className)}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-2">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2">
          {right}
          {table && (
            <button
              onClick={() => setShowTable((v) => !v)}
              className={clsx(
                "inline-flex items-center gap-1 rounded-md border border-line px-2 py-1 text-[11px] text-ink-2 hover:bg-surface-2",
                showTable && "bg-surface-2 text-ink",
              )}
              aria-pressed={showTable}
            >
              <Table2 size={12} /> Table
            </button>
          )}
        </div>
      </div>
      {legend && <div className="mb-2">{legend}</div>}
      {error ? (
        <ErrorState error={error} />
      ) : loading ? (
        <div className="h-56 animate-pulse rounded-lg bg-surface-2" />
      ) : showTable && table ? (
        <DataTable columns={table.columns} rows={table.rows} maxHeight={320} />
      ) : (
        children
      )}
    </Card>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = (error as Error)?.message ?? String(error);
  return (
    <div className="rounded-lg border border-dashed border-line p-6 text-sm text-ink-2">
      <div className="mb-1 flex items-center gap-2 font-medium text-ink">
        <AlertTriangle size={15} className="text-warning" /> Data not available
      </div>
      {msg}
      <div className="mt-2 text-xs text-muted">
        Start the backend and run <code className="font-mono">python -m gridalpha.cli run --quick</code> (or use “Run pipeline”).
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Table
export function DataTable({
  columns,
  rows,
  maxHeight,
  align,
}: {
  columns: ReactNode[];
  rows: ReactNode[][];
  maxHeight?: number;
  align?: ("left" | "right")[];
}) {
  return (
    <div className="overflow-auto rounded-lg border border-line" style={{ maxHeight }}>
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-surface-2 text-xs text-ink-2">
          <tr>
            {columns.map((c, i) => (
              <th key={i} className={clsx("px-3 py-2 font-medium whitespace-nowrap", (align?.[i] ?? (i ? "right" : "left")) === "right" ? "text-right" : "text-left")}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line hover:bg-surface-2/60">
              {r.map((v, j) => (
                <td key={j} className={clsx("px-3 py-1.5 whitespace-nowrap", (align?.[j] ?? (j ? "right" : "left")) === "right" ? "text-right" : "text-left")}>
                  {v ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ Controls
export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-line bg-surface p-0.5 text-xs">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx("rounded px-2.5 py-1 transition-colors", value === o.value ? "bg-surface-3 font-medium text-ink" : "text-ink-2 hover:text-ink")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function SliderField({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  hint?: string;
}) {
  return (
    <label className="block">
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-ink-2" title={hint}>
          {label}
        </span>
        <span className="font-medium tabular text-ink">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        className="w-full"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
