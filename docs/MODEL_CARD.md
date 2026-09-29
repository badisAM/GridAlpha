# Model card — GridAlpha day-ahead price forecaster & dispatch policy

## Intended use
* **Task.** Forecast the 24 hourly day-ahead clearing prices of the German–Luxembourg bidding zone for delivery day D, issued at D-1 ≤ 11:00
  Europe/Berlin (before the 12:00 CET SDAC gate closure), as quantiles P10 / P50 / P90; convert them into a committed battery schedule.
* **Users.** Battery-storage operators, optimisers / route-to-market providers, utility trading desks — as *decision support*: a trader reviews
  the brief and signs the bid.
* **Out of scope.** Intraday / balancing markets, price-maker bidding for fleets large enough to move the price, other bidding zones
  without re-validation.

## Data
| Source | Content | Resolution | Licence |
|---|---|---|---|
| Energy-Charts (Fraunhofer ISE) / SMARD | day-ahead price, load, solar, wind on/offshore | 15 min → hourly mean | CC BY 4.0 |
| Open-Meteo historical-forecast & forecast APIs | temperature, 100 m wind, shortwave radiation, cloud cover at 8 sites | hourly | free, non-commercial |
| Yahoo Finance chart API | TTF front-month gas | daily | public quotes (optional input) |
| Calibrated simulator | same schema, used only when the APIs are unreachable | hourly | synthetic |

History starts 2023-01-01. Weather is always a *forecast* (as available at bidding time) — never observations.

## Features (37)
Calendar (hour, weekday, holidays, seasonality) · weather forecasts & clear-sky geometry · **fundamental proxies**: solar and wind infeed
(weather × online-estimated fleet capacity), demand (same-weekday profile), **residual load** and its daily rank/min/max/delta ·
price memory (D-1, D-2, D-7 same hour, D-1 statistics, 7-day hourly profile, negative hours) · TTF gas (lag 2 d) · realised residual load
(lag 48 h). All lags are ≥ the publication delay of their source (see `features/builder.py`, tested in `tests/test_features.py`).

## Models
| Model | Type | Output | Notes |
|---|---|---|---|
| naive D-1 / D-7, 7-day profile | baselines | P50 + empirical residual quantiles by hour | what the model must beat |
| LightGBM quantile | gradient boosting, 3 boosters | P10/P50/P90 | 220 rounds, lr 0.1, recency half-life 180 d |
| TiDE | PyTorch MLP encoder–decoder | P10/P50/P90 (monotone head) | 7-day lookback, 19 future covariates, 2-seed ensemble, warm-start fine-tuning |
| Ensemble | online softmax of 28-day relative pinball loss | quantile average | + adaptive conformal scaling toward 80 % coverage |

## Evaluation protocol
Walk-forward over the last 365 delivery days; expanding-window retraining every 28 days; ensemble weights and conformal scale updated
daily from settled days only; every strategy optimised by the same MILP and settled at realised prices. Metrics: MAE, RMSE, pinball,
P10–P90 coverage and width, Kendall τ per day, peak/trough-hour hit (±1 h), capture ratio, P&L tail statistics.
Latest numbers: `backend/artifacts/reports/kpi_report.md` (regenerated on every run) and the **Models** page.

## Known limitations
* **Synthetic fallback.** Figures produced in simulator mode demonstrate the method, not market performance; rerun with internet access
  (`GRIDALPHA_DATA_MODE=live`) to report market results.
* **Hourly MTU** (the market is 15-min since Oct 2025) and **price-taker** assumption (valid for a 10–50 MW asset).
* **Extreme events** (scarcity spikes, gas shocks) are under-represented; the conformal layer widens bands after misses but lags a regime
  break by a few days.
* **Tree extrapolation**: gas or price levels outside the training range are flagged by the out-of-distribution monitor.
* λ (risk aversion) default was chosen at the knee of the backtest frontier; a production choice should be validated on a separate year.

## Responsible operation
Human-in-the-loop bid approval; deterministic, auditable numbers (the optional LLM only rephrases facts); data mode surfaced everywhere;
retraining guard-rail in the registry; all decisions reproducible from the lake snapshot and the model version.
