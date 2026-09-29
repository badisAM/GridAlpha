// Entity -> colour is FIXED (never by rank), so filtering never repaints a
// survivor. Values are CSS variables defined per theme in globals.css; the
// palette was validated for CVD separation in light and dark mode.
export const SERIES: Record<string, string> = {
  ensemble_cvar: "var(--s1)",
  ensemble: "var(--s1)",
  lgbm: "var(--s2)",
  tide: "var(--s3)",
  naive_d1: "var(--s4)",
  profile7: "var(--s5)",
  naive_d7: "var(--s6)",
  oracle: "var(--ref)",
  actual: "var(--ink)",
};

export const C = {
  s1: "var(--s1)",
  s2: "var(--s2)",
  s3: "var(--s3)",
  s4: "var(--s4)",
  s5: "var(--s5)",
  s6: "var(--s6)",
  ref: "var(--ref)",
  ink: "var(--ink)",
  ink2: "var(--ink-2)",
  muted: "var(--muted)",
  grid: "var(--grid)",
  axis: "var(--axis)",
  surface: "var(--surface)",
  charge: "var(--s2)",
  discharge: "var(--s3)",
  good: "var(--good)",
  warning: "var(--warning)",
  serious: "var(--serious)",
  critical: "var(--critical)",
  divNeg: "var(--div-neg)",
  divPos: "var(--div-pos)",
};
