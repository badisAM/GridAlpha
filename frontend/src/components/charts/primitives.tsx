"use client";

import type { ReactNode } from "react";

// Shared chart chrome: hairline solid grid, recessive axes, one tooltip style.
export const AXIS = {
  tickLine: false,
  axisLine: { stroke: "var(--axis)" },
  tick: { fontSize: 11, fill: "var(--muted)" },
} as const;

export const GRID = { stroke: "var(--grid)", vertical: false } as const;

export const CURSOR = { stroke: "var(--axis)", strokeWidth: 1 } as const;

type Row = { name: string; value: ReactNode; color?: string; kind?: "line" | "bar" | "band" };

export function TipBox({ title, rows }: { title: ReactNode; rows: Row[] }) {
  return (
    <div className="min-w-[160px] rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <div className="mb-1 font-medium text-ink">{title}</div>
      <div className="space-y-0.5">
        {rows.map((r) => (
          <div key={r.name} className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-1.5 text-ink-2">
              {r.color &&
                (r.kind === "bar" ? (
                  <span className="size-2 rounded-sm" style={{ background: r.color }} />
                ) : r.kind === "band" ? (
                  <span className="h-2 w-3 rounded-sm" style={{ background: r.color, opacity: 0.3 }} />
                ) : (
                  <span className="h-0.5 w-3 rounded-full" style={{ background: r.color }} />
                ))}
              {r.name}
            </span>
            <span className="tabular font-medium text-ink">{r.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Recharts tooltip adapter: `render(datum)` returns the rows to show. */
export function makeTip<T>(title: (d: T) => ReactNode, render: (d: T) => Row[]) {
  return function Tip(props: { active?: boolean; payload?: readonly { payload?: T }[] }) {
    const d = props.payload?.[0]?.payload;
    if (!props.active || !d) return null;
    return <TipBox title={title(d)} rows={render(d)} />;
  };
}
