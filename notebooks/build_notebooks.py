"""Generates the three analysis notebooks (source of truth kept in Python so
they diff cleanly). Run:  python notebooks/build_notebooks.py [--execute]"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).resolve().parent

SETUP = r'''
import sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path.cwd().resolve()
while not (ROOT / "backend").exists() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "backend"))

import numpy as np, pandas as pd, matplotlib.pyplot as plt
from gridalpha.data.lake import get_lake
from gridalpha.data.ingest import ingest

plt.rcParams.update({"figure.figsize": (11, 4), "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e1e0d9", "grid.linewidth": 0.8, "font.size": 10})
BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#898781"
lake = get_lake()
if not lake.exists("market_hourly"):
    ingest()          # auto: public APIs, falls back to the calibrated simulator
meta = lake.read_json("data_meta")
print("data mode:", meta["mode"], "| rows:", meta["rows"], "| last price:", meta["last_price_ts"])
'''


def md(s: str):
    return nbf.v4.new_markdown_cell(s.strip())


def code(s: str):
    return nbf.v4.new_code_cell(s.strip())


def nb_eda():
    return [
        md("""
# 01 · Market EDA — where does a battery make money?

**Question.** A battery earns by buying cheap hours and selling expensive ones on the German–Luxembourg day-ahead market.
Before modelling anything, we check *how much* spread there is, *when* it happens and *what drives it*.

Data: hourly day-ahead prices, load, wind and solar (Energy-Charts / SMARD, CC BY 4.0), weather forecasts (Open-Meteo) and
TTF gas (Yahoo). If the APIs are unreachable the pipeline switches to the calibrated fundamental simulator — the mode is printed below.
"""),
        code(SETUP),
        code(r'''
df = lake.read("market_hourly").copy()
loc = df.index.tz_convert("Europe/Berlin")
df["date"], df["hour"], df["year"], df["month"] = loc.date, loc.hour, loc.year, loc.month
px = df.dropna(subset=["price"])
daily = px.groupby("date")["price"].agg(["mean", "min", "max"])
daily["spread"] = daily["max"] - daily["min"]
summary = px.groupby("year").agg(mean=("price", "mean"), p5=("price", lambda s: s.quantile(.05)),
                                 p95=("price", lambda s: s.quantile(.95)), min=("price", "min"),
                                 neg_hours=("price", lambda s: int((s < 0).sum())))
summary["avg_daily_spread"] = daily.groupby(pd.to_datetime(daily.index).year)["spread"].mean()
summary.round(1)
'''),
        md("""
**Reference (real market, 2025):** mean ≈ 89 €/MWh, ≈ 573 negative hours, average daily spread ≈ 130 €/MWh, record low −250 €/MWh
(Bloomberg/Montel, FfE). Negative hours keep rising with solar build-out — that is exactly the raw material of storage.
"""),
        code(r'''
prof = px[px.year == px.year.max()].pivot_table(index="month", columns="hour", values="price", aggfunc="mean")
fig, ax = plt.subplots(figsize=(11, 4))
im = ax.imshow(prof, aspect="auto", cmap="Blues")
ax.set(xlabel="hour (local)", ylabel="month", title=f"Average price by month × hour — the duck curve ({px.year.max()})")
fig.colorbar(im, label="€/MWh"); plt.show()
'''),
        code(r'''
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
neg = px.assign(neg=px.price < 0).groupby(["year", "month"])["neg"].sum().unstack(0)
neg.plot(kind="bar", ax=axes[0], color=[BLUE, ORANGE, AQUA, YELLOW][: neg.shape[1]], width=0.8)
axes[0].set(title="Negative-price hours per month", xlabel="month", ylabel="hours")
by_hour = px.assign(neg=px.price < 0).groupby("hour")["neg"].mean() * 100
axes[1].bar(by_hour.index, by_hour.values, color=BLUE)
axes[1].set(title="Share of hours with negative prices, by hour", xlabel="hour", ylabel="%")
plt.tight_layout(); plt.show()
'''),
        md("""
## The merit order in one picture
Prices are set by the most expensive plant needed. What matters is **residual load** = load − wind − solar: when renewables
cover the load, price collapses (even below zero); when they don't, gas plants set the price.
"""),
        code(r'''
px = px.assign(residual=(px.load - px.solar - px.wind_onshore - px.wind_offshore) / 1000)
s = px.sample(min(8000, len(px)), random_state=0)
fig, ax = plt.subplots(figsize=(8, 5))
sc = ax.scatter(s.residual, s.price, c=s.ttf, s=4, cmap="viridis", alpha=.6)
ax.axhline(0, color=GRAY, lw=1)
ax.set(xlabel="residual load (GW)", ylabel="price (€/MWh)", title="Merit order: price vs residual load (colour = TTF gas)")
fig.colorbar(sc, label="TTF €/MWh"); plt.show()
print("correlation price ~ residual load:", round(px[["price", "residual"]].corr().iloc[0, 1], 3))
'''),
        md("""
## How much is perfect foresight worth?
Upper bound of day-ahead arbitrage for a 1 MW / 2 MWh battery (88 % round-trip, ≤ 1.5 cycles/day) solved as a MILP per day.
Every forecast-driven strategy is measured as a **capture ratio** against this ceiling.
"""),
        code(r'''
from gridalpha.trading.battery import BatterySpec, optimise
spec = BatterySpec(power_mw=1, energy_mwh=2, rte=0.88, max_cycles_per_day=1.5, degradation_eur_per_mwh=0,
                   soc_min_frac=0, soc_max_frac=1)
last365 = px[px.date >= (pd.Timestamp(px.date.max()) - pd.Timedelta(days=364)).date()]
rev = {d: optimise(spec, g.price.to_numpy()).expected_pnl for d, g in last365.groupby("date")}
rev = pd.Series(rev)
print(f"perfect-foresight revenue, last 365 days: {rev.sum():,.0f} €/MW  |  mean {rev.mean():,.0f} €/day  |  "
      f"best day {rev.max():,.0f} €  |  worst day {rev.min():,.0f} €")
rev.index = pd.to_datetime(rev.index)
rev.rolling(14).mean().plot(color=BLUE, title="Perfect-foresight revenue per MW, 14-day rolling mean (€/day)"); plt.show()
'''),
        md("""
**Takeaways**
1. The value is concentrated in a few hours per day (solar trough → evening peak) and it is seasonal.
2. Residual load explains most of the price level (strong monotone relation) → it is the backbone feature of the models.
3. The ceiling is known; the business question becomes *how much of it can a forecast capture?* → notebook 03.
"""),
    ]


def nb_models():
    return [
        md("""
# 02 · Forecasting models — probabilistic day-ahead prices

Setting: at **D-1 11:00** (before the 12:00 CET gate closure) forecast the 24 hourly prices of day D, with uncertainty.

* **Information set is enforced** by construction and by a unit test (`tests/test_features.py` perturbs the future and checks
  nothing moves): price lags ≥ 1 day, generation/load lags ≥ 48 h, weather = *forecasts*, gas lagged 2 days.
* Models: naive baselines · **LightGBM quantile regression** (P10/P50/P90) · **TiDE** (Google's Time-series Dense Encoder, PyTorch)
  · online ensemble + adaptive conformal calibration (in the backtest).
"""),
        code(SETUP),
        code(r'''
from gridalpha.features.builder import build_features, FEATURES, training_rows
feat = build_features(lake.read("market_hourly"))
print(len(FEATURES), "features");
feat[FEATURES].describe().T[["mean", "std", "min", "max"]].round(2).head(15)
'''),
        code(r'''
from gridalpha.models.baselines import NaiveD1, Profile7
from gridalpha.models.lgbm import LGBMQuantile, global_shap_importance
from gridalpha.models.metrics import forecast_metrics
days_all = sorted(training_rows(feat)["delivery_date"].unique())
cut = pd.Timestamp(days_all[-60])                       # hold out the last 60 delivery days
test_days = [pd.Timestamp(d) for d in days_all[-60:]]
res, preds = {}, {}
for M in (NaiveD1, Profile7, LGBMQuantile):
    m = M().fit(feat, cut)
    p = m.predict(feat, test_days).join(feat[["price", "delivery_date"]]).rename(columns={"price": "actual"})
    preds[m.name], res[m.name] = p, forecast_metrics(p)
    if m.name == "lgbm": lgbm = m
'''),
        code(r'''
try:
    from gridalpha.models.tide import TiDEQuantile, TORCH_OK
    if TORCH_OK:
        t = TiDEQuantile(seeds=1).fit(feat, cut)
        p = t.predict(feat, test_days).join(feat[["price", "delivery_date"]]).rename(columns={"price": "actual"})
        preds["tide"], res["tide"] = p, forecast_metrics(p)
        print(t.history)
except Exception as e:
    print("TiDE skipped:", e)
pd.DataFrame(res).T[["mae", "rmse", "pinball", "coverage_80", "kendall_tau", "peak_hour_hit", "trough_hour_hit"]].round(3)
'''),
        md("""
Reading the table: MAE/RMSE/pinball measure accuracy; **coverage_80** should be ≈ 0.80 for a calibrated P10–P90 band (raw GBM quantiles
are usually too narrow → the backtest applies adaptive conformal scaling); **Kendall τ / peak-hour hit** measure whether the hours are
*ranked* correctly — what a battery actually monetises.
"""),
        code(r'''
d = preds["lgbm"][preds["lgbm"].delivery_date == test_days[-3]].sort_index()
fig, ax = plt.subplots()
x = d.index.tz_convert("Europe/Berlin").hour
ax.fill_between(x, d.q10, d.q90, color=BLUE, alpha=.15, label="LightGBM P10–P90")
ax.plot(x, d.q50, color=BLUE, lw=2, label="LightGBM P50")
ax.plot(x, d.actual, color="black", lw=1.5, label="realised")
nd = preds["naive_d1"].loc[d.index]
ax.plot(x, nd.q50, color=YELLOW, lw=1.5, label="naive D-1")
ax.set(title=f"Forecast vs realised — {test_days[-3].date()}", xlabel="hour", ylabel="€/MWh"); ax.legend(); plt.show()
'''),
        md("## Explainability — TreeSHAP (native in LightGBM, no extra dependency)"),
        code(r'''
imp = global_shap_importance(lgbm, feat[feat.delivery_date.isin(test_days)])
imp.head(12)[::-1].plot(kind="barh", color=BLUE, figsize=(8, 5), title="Mean |SHAP| share (%) — hold-out period"); plt.show()
'''),
        code(r'''
rows = feat[feat.delivery_date == test_days[-1]]
sv = lgbm.shap(rows).drop(columns="_base")
top = sv.abs().mean().sort_values(ascending=False).index[:6]
sv[top].set_index(rows.hour).plot(kind="bar", stacked=True, figsize=(12, 4),
    color=[BLUE, ORANGE, AQUA, YELLOW, MAGENTA, GREEN], title=f"Per-hour SHAP contributions (€/MWh) — {test_days[-1].date()}")
plt.show()
'''),
        md("""
## Error by hour — where is the problem hard?
"""),
        code(r'''
eh = pd.DataFrame({k: (v.actual - v.q50).abs().groupby(v.index.tz_convert("Europe/Berlin").hour).mean() for k, v in preds.items()})
eh.plot(color=[YELLOW, MAGENTA, ORANGE, AQUA][: eh.shape[1]], title="MAE by hour (€/MWh)", xlabel="hour"); plt.show()
'''),
        md("""
**Takeaways**
* Gradient boosting on well-designed fundamental features (residual-load proxies, price memory) is the strongest single model —
  the merit order is piecewise, which trees capture naturally.
* TiDE brings a different inductive bias (multi-horizon, whole-day shape) → useful in the ensemble on regime changes; its weight is
  learned online from recent pinball loss rather than fixed by hand.
* Calibration matters as much as accuracy for the decision layer: scenarios are sampled from these quantiles (notebook 03).
"""),
    ]


def nb_trading():
    return [
        md("""
# 03 · From forecast to money — battery optimisation & walk-forward backtest

1. Formulate the daily battery dispatch as a **MILP** (HiGHS via SciPy) with power, energy, efficiency, cycle and degradation constraints.
2. Make it **risk-aware**: Gaussian-copula price scenarios from the quantile forecast + **CVaR** (Rockafellar–Uryasev).
3. Read the **walk-forward backtest** produced by the pipeline and measure value in euros (capture ratio vs perfect foresight).
"""),
        code(SETUP),
        code(r'''
from gridalpha.trading.battery import BatterySpec, optimise, settle
from gridalpha.trading.scenarios import quantile_scenarios
spec = BatterySpec(power_mw=10, energy_mwh=20, rte=0.88, max_cycles_per_day=1.5, degradation_eur_per_mwh=8)
if not lake.exists("bt_forecasts"):
    raise SystemExit("run the pipeline first:  python -m gridalpha.cli run --quick")
fc = lake.read("bt_forecasts")
ens_all = fc[fc.model == "ensemble"]
recent = ens_all[ens_all.delivery_date > ens_all.delivery_date.max() - pd.Timedelta(days=90)]
# pick the most uncertain recent day (widest P10–P90 band): that's where risk control matters
day = (recent.q90 - recent.q10).groupby(recent.delivery_date).mean().idxmax()
e = ens_all[ens_all.delivery_date == day].sort_values("ts")
q10, q50, q90, actual = (e[c].to_numpy() for c in ("q10", "q50", "q90", "actual"))
det = optimise(spec, q50)
orc = optimise(spec, actual)
print(f"{pd.Timestamp(day).date()}: expected {det.expected_pnl:,.0f} € | realised {settle(actual, det.charge, det.discharge, spec):,.0f} € "
      f"| perfect foresight {orc.expected_pnl:,.0f} € | solve {det.solve_ms:.1f} ms")
'''),
        code(r'''
h = np.arange(len(q50))
fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
a1.fill_between(h, q10, q90, color=BLUE, alpha=.15, label="P10–P90"); a1.plot(h, q50, color=BLUE, lw=2, label="forecast P50")
a1.plot(h, actual, color="black", lw=1.4, label="realised"); a1.set_ylabel("€/MWh"); a1.legend()
a2.bar(h, det.discharge, color=AQUA, label="discharge"); a2.bar(h, -det.charge, color=ORANGE, label="charge")
a2.set_ylabel("MW"); a2.set_xlabel("hour"); a2.legend(); plt.tight_layout(); plt.show()
'''),
        md("""
## Risk: expected P&L vs CVaR
One schedule, 200 correlated price scenarios. Increasing λ trades a little expected profit for a better worst-5 % outcome.
"""),
        code(r'''
sc = quantile_scenarios(q10, q50, q90, n=200, rho=0.85, seed=1)
pts = []
for lam in (0, .1, .2, .3, .5, .7, .9):
    r = optimise(spec, q50, sc, risk_aversion=lam)
    pts.append({"lambda": lam, "E[P&L]": r.scenario_pnl.mean(), "CVaR95": r.risk()["cvar"], "cycles": r.discharge.sum() / spec.energy_mwh})
front = pd.DataFrame(pts); print(front.round(1).to_string(index=False))
plt.plot(front["CVaR95"], front["E[P&L]"], "-o", color=BLUE)
for _, r in front.iterrows(): plt.annotate(f"λ={r['lambda']}", (r["CVaR95"], r["E[P&L]"]), fontsize=8)
plt.xlabel("CVaR 95 % (€)"); plt.ylabel("expected P&L (€)"); plt.title("Risk / return frontier"); plt.show()
'''),
        md("## Walk-forward backtest (written by the pipeline)"),
        code(r'''
summ = lake.read_json("bt_summary")
tm = pd.DataFrame(summ["trading_metrics"]).T.sort_values("total_pnl_eur", ascending=False)
print(summ["period"]); tm[["total_pnl_eur", "eur_per_mw_year", "capture_ratio", "worst_day_eur", "loss_day_share", "avg_cycles_per_day"]]
'''),
        code(r'''
daily = lake.read("bt_daily").pivot_table(index="delivery_date", columns="strategy", values="pnl")
cols = {"oracle": GRAY, "ensemble_cvar": BLUE, "lgbm": ORANGE, "tide": AQUA, "profile7": MAGENTA, "naive_d1": YELLOW}
daily[[c for c in cols if c in daily]].cumsum().plot(color=[cols[c] for c in cols if c in daily], title="Cumulative P&L (€)")
plt.show()
'''),
        md("""
## Does accuracy or ranking drive money?
Per day, correlate the capture ratio of the ensemble strategy with its MAE and with its Kendall τ.
"""),
        code(r'''
from scipy.stats import kendalltau, spearmanr
e = fc[fc.model == "ensemble"]
per_day = e.groupby("delivery_date").apply(lambda g: pd.Series({
    "mae": (g.actual - g.q50).abs().mean(), "tau": kendalltau(g.actual, g.q50).statistic}))
cap = (daily["ensemble"] / daily["oracle"]).rename("capture")
j = per_day.join(cap).dropna()
print("Spearman(capture, tau) =", round(spearmanr(j.capture, j.tau).statistic, 3),
      "| Spearman(capture, MAE) =", round(spearmanr(j.capture, j.mae).statistic, 3))
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].scatter(j.tau, j.capture.clip(-.5, 1.05), s=10, color=BLUE); ax[0].set(xlabel="Kendall τ (day)", ylabel="capture ratio")
ax[1].scatter(j.mae, j.capture.clip(-.5, 1.05), s=10, color=ORANGE); ax[1].set(xlabel="MAE (day)", ylabel="capture ratio")
plt.tight_layout(); plt.show()
'''),
        md("""
**Takeaways**
* The decision layer turns forecast quality into euros; the capture ratio is the KPI a trading desk actually cares about.
* Ranking quality (τ) is tightly linked to captured value — consistent with recent literature (arXiv:2604.12082).
* Risk aversion costs little expected profit and reduces cycling (battery wear) — a knob the trader controls in the UI.
"""),
    ]


def build(execute: bool = False) -> None:
    books = {"01_market_eda.ipynb": nb_eda(), "02_forecasting_models.ipynb": nb_models(),
             "03_battery_trading_backtest.ipynb": nb_trading()}
    for name, cells in books.items():
        nb = nbf.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}})
        path = HERE / name
        if execute:
            from nbconvert.preprocessors import ExecutePreprocessor

            ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(HERE)}})
        nbf.write(nb, path)
        print("wrote", path)


if __name__ == "__main__":
    build(execute="--execute" in sys.argv)
