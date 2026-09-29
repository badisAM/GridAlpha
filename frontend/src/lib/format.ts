const TZ = "Europe/Berlin";

export const eur = (v: number | null | undefined, digits = 0) =>
  v == null || !isFinite(v)
    ? "—"
    : new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "EUR",
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(v);

export const compactEur = (v: number | null | undefined) =>
  v == null || !isFinite(v)
    ? "—"
    : new Intl.NumberFormat("en-GB", {
        style: "currency",
        currency: "EUR",
        notation: "compact",
        maximumFractionDigits: 1,
      }).format(v);

export const num = (v: number | null | undefined, digits = 1) =>
  v == null || !isFinite(v)
    ? "—"
    : new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);

export const int = (v: number | null | undefined) =>
  v == null || !isFinite(v) ? "—" : new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 }).format(v);

export const pct = (v: number | null | undefined, digits = 1) =>
  v == null || !isFinite(v) ? "—" : `${(v * 100).toFixed(digits)} %`;

export const signedPct = (v: number | null | undefined, digits = 1) =>
  v == null || !isFinite(v) ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(digits)} %`;

export const price = (v: number | null | undefined) => (v == null ? "—" : `${num(v, 1)} €/MWh`);

const hourFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
const dayHourFmt = new Intl.DateTimeFormat("en-GB", {
  timeZone: TZ,
  weekday: "short",
  day: "2-digit",
  hour: "2-digit",
});
const dayFmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short" });
const longDayFmt = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

export const hourLabel = (iso: string) => hourFmt.format(new Date(iso));
export const dayHourLabel = (iso: string) => dayHourFmt.format(new Date(iso));
export const dayLabel = (d: string) => dayFmt.format(new Date(`${d}T12:00:00`));
export const longDay = (d: string | null | undefined) => (d ? longDayFmt.format(new Date(`${d}T12:00:00`)) : "—");

export const ago = (iso: string | null | undefined) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};

export const MODEL_LABEL: Record<string, string> = {
  oracle: "Perfect foresight",
  ensemble_cvar: "AI ensemble + CVaR",
  ensemble: "AI ensemble",
  lgbm: "LightGBM quantile",
  tide: "TiDE (deep learning)",
  profile7: "7-day profile",
  naive_d1: "Naive D-1",
  naive_d7: "Naive D-7",
};

export const FEATURE_LABEL: Record<string, string> = {
  res_proxy: "Residual load",
  solar_proxy: "Solar forecast",
  wind_proxy: "Wind forecast",
  load_proxy: "Demand forecast",
  p_lag1d: "Price D-1 (same hour)",
  p_lag2d: "Price D-2 (same hour)",
  p_lag7d: "Price D-7 (same hour)",
  p_d1_mean: "Price D-1 mean",
  p_d1_std: "Price D-1 volatility",
  p_d1_max: "Price D-1 max",
  p_d1_min: "Price D-1 min",
  p_d1_neg_h: "Negative hours D-1",
  p_d7_mean: "Price 7-day mean",
  p_hour_mean7: "7-day hourly profile",
  ttf_lag: "TTF gas price",
  res_proxy_rank: "Residual-load rank",
  res_proxy_day_mean: "Residual load (day mean)",
  res_proxy_day_min: "Residual load (day min)",
  res_proxy_day_max: "Residual load (day max)",
  res_proxy_delta_d1: "Residual load vs D-1",
  ren_share_proxy: "Renewable share",
  temp_fc: "Temperature",
  wind100_n_fc: "Wind speed 100 m",
  rad_s_fc: "Solar radiation",
  cloud_fc: "Cloud cover",
  clear_sky: "Clear-sky geometry",
  wind_cf_fc: "Wind capacity factor",
  res_act_lag48: "Residual load (D-2 actual)",
  hour: "Hour of day",
  hour_sin: "Hour (sin)",
  hour_cos: "Hour (cos)",
  dow: "Day of week",
  month: "Month",
  is_offday: "Weekend / holiday",
  is_holiday: "Public holiday",
  doy_sin: "Seasonality (sin)",
  doy_cos: "Seasonality (cos)",
};

export const featureLabel = (f: string) => FEATURE_LABEL[f] ?? f;
