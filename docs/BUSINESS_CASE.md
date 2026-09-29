# Business case — why automate battery trading with AI?

> **Résumé (FR).** Les batteries raccordées au réseau gagnent de l'argent en achetant l'électricité aux heures creuses (souvent à prix
> négatif, quand le solaire sature le réseau) et en la revendant à la pointe du soir. La valeur dépend entièrement de la qualité de la
> décision prise **avant 12 h (clôture de l'enchère day-ahead)**. GridAlpha automatise toute la chaîne — collecte, prévision probabiliste,
> optimisation sous risque, contrôle — et en mesure la valeur en euros. Sur 365 jours de backtest walk-forward, la stratégie IA capte
> **89,7 %** du revenu théorique maximal contre **54,1 %** pour la pratique naïve (+65,8 %, soit **+225 k€/an pour 10 MW**).

## 1. The problem

| Market fact (Germany, DE-LU zone) | Value | Source |
|---|---|---|
| Negative day-ahead price hours, 2025 | ≈ 573 h (record; 457 h in 2024) | Bloomberg / Montel |
| Average daily price spread, 2025 | ≈ 130 €/MWh | FfE analysis of EPEX Spot |
| Lowest day-ahead price, 2025 | −250 €/MWh (11 May) | FfE |
| Grid-scale batteries, end of 2025 | 2.4 GW / 3.5 GWh, ~5.6 GW scheduled 2026-27 | Modo Energy |
| All-in BESS capex outside China/US (Oct 2025) | ≈ $125/kWh (large 4 h projects) | Ember |
| Perfect-foresight day-ahead arbitrage value (1 MW / 2 h) | ≈ 61–85 k€/MW/yr | arXiv:2608.08377; open benchmark `fr4borsa/bess-arbitrage` on Energy-Charts data |
| Share of that ceiling captured by forecast-driven strategies | ~66–98 % depending on method | arXiv:2604.12082; Energies 18(13):3309 |

Every day before 12:00 CET a battery operator must commit 24 hourly positions without knowing tomorrow's prices. A wrong ranking of
the hours — charging at 10:00 instead of 12:00, discharging at 18:00 instead of 20:00 — silently destroys value. Many desks still bid
with simple rules (yesterday's prices, an average profile) prepared by hand in spreadsheets.

**Who pays for the solution:** BESS owners, optimisers / route-to-market providers, utilities' trading desks — and energy-tech
companies building these products (smart-energy, metering and grid players).

## 2. Value chain and KPI tree

```
Revenue (€/MW/yr) = ceiling(market volatility)  ×  capture ratio(decision quality)  −  degradation(cycles)
                                                    ▲
             forecast ranking quality (Kendall τ, peak-hour hit) + calibration (coverage) + risk control (CVaR)
```

The market sets the ceiling; **the decision layer sets the capture ratio** — that is the lever GridAlpha controls and measures.
In the backtest, days where the ensemble ranks hours well (high τ) are the days with high capture (Spearman ρ = 0.59), while daily MAE is
only weakly related (ρ = −0.22) — which is why DSO3/DSO4 target ranking, not only accuracy.

## 3. Objectives — Business (BO) and Data-Science (DSO)

Targets were fixed from the literature range and a simple desk practice baseline; achieved values come from the latest
walk-forward run (365 delivery days, 10 MW / 20 MWh, 88 % round-trip, ≤ 1.5 cycles/day, 8 €/MWh degradation) and are regenerated in
`backend/artifacts/reports/kpi_report.md` at every pipeline run.

| ID | Objective | KPI | Target | Achieved | Status |
|---|---|---|---|---|---|
| **BO1** | Capture most of the theoretical arbitrage value | capture ratio vs perfect foresight | ≥ 85 % (stretch 90 %) | **89.7 %** | ✅ |
| **BO2** | Beat current desk practice (naive D-1 schedule) | revenue uplift vs naive | ≥ +15 % | **+65.8 % (+225 k€/yr per 10 MW)** | ✅ |
| **BO3** | Automate the daily bidding workflow end-to-end | wall-clock ingest → bid · success rate | < 10 min · 100 % | **5–7 min · 100 %** | ✅ |
| **BO4** | Control downside risk | share of loss-making days | ≤ 2 % | **0.8 %** (naive 15.9 %) | ✅ |
| **BO5** | Support the investment decision with measured revenue | backtested €/MW/yr → NPV/IRR | reported | **56.8 k€/MW/yr** | ✅ |
| **DSO1** | Point accuracy | MAE reduction vs naive D-1 | ≥ 40 % | **−60.3 %** (14.6 vs 36.9 €/MWh) | ✅ |
| **DSO2** | Calibrated uncertainty | P10–P90 empirical coverage | 75–85 % | **79.8 %** (raw GBM 60.6 %) | ✅ |
| **DSO3** | Rank the hours correctly | mean Kendall τ per day | ≥ 0.75 | **0.768** (naive 0.489) | ✅ |
| **DSO4** | Time the peak | peak-hour hit rate (±1 h) | ≥ 80 % | **80.3 %** (naive 52 %) | ✅ |
| **DSO5** | Real-time serving | API p95 latency (reads) | < 150 ms | **8.8 ms** | ✅ |
| **DSO6** | Fast decisions | MILP solve time | < 100 ms | **18 ms** | ✅ |

Mapping: DSO1–DSO4 drive BO1/BO2 (better ranking → higher capture); DSO2 + CVaR drive BO4; DSO5/DSO6 make BO3 possible (the whole
loop fits well inside the 90-minute buffer between the 10:30 run and gate closure).

## 4. What the risk layer buys

| 365-day backtest | AI ensemble (risk-neutral) | AI ensemble + CVaR (λ = 0.1) | Naive D-1 |
|---|---|---|---|
| Capture ratio | 90.4 % | 89.7 % | 54.1 % |
| Worst day | −596 € | **−307 €** | −1,704 € |
| Average of the worst 5 % days | 58 € | **94 €** | −953 € |
| Cycles per day (wear) | 1.32 | **1.28** | 1.33 |

For 0.7 pt of capture the CVaR layer halves the worst-day loss and reduces cycling by ~3 %. λ is a business knob: the trader moves along
the risk/return frontier in the UI.

## 5. Investment view (10 MW / 20 MWh, day-ahead arbitrage only)

Assumptions: 180 €/kWh all-in capex (conservative vs Ember's ≈ $125/kWh for large 4 h projects), fixed opex 2 % of capex/yr,
15 years, WACC 8 %, revenue −2 %/yr (fade + cannibalisation).

| Decision layer | Year-1 revenue | NPV | IRR | Payback |
|---|---|---|---|---|
| **GridAlpha (AI + CVaR)** | 568 k€ | **+140 k€** | **8.7 %** | **7.9 years** |
| Naive D-1 schedule | 342 k€ | −1.6 M€ | −0.8 % | beyond lifetime |

Same asset, same market: the decision layer is the difference between a bankable and a non-bankable project on day-ahead revenue
alone (real projects also stack intraday and balancing revenues — see roadmap). Try other assumptions live on the **Business case** page.

**Portfolio view.** One percentage point of capture on the German grid-scale fleet (2.4 GW) at a 61–85 k€/MW/yr ceiling is worth
≈ 1.5–2.0 M€ per year — the order of magnitude that justifies a forecasting & optimisation team.

## 6. Automation value

| Task (daily, before 12:00 CET) | Manual practice | GridAlpha |
|---|---|---|
| Pull prices, generation, weather, gas | copy/paste from several portals | scraped with retries, cached, quality-gated |
| Forecast tomorrow | yesterday's curve / average profile | calibrated quantile ensemble + explanation |
| Build the schedule | spreadsheet rules | exact MILP with physical & warranty constraints, risk-aware |
| Check risk | gut feeling | 100 scenarios, CVaR, probability of loss |
| Report & learn | ad hoc | brief + alerts, backtest, drift & latency monitoring, model registry |
| Time | ~1–2 h analyst time (assumption) | **5–7 min unattended** at 10:30, human reviews and signs |

## 7. Risks, limits and how they are handled

| Risk | Mitigation in the project |
|---|---|
| Look-ahead bias inflating results | explicit information set + unit test that tampers with the future |
| Over-optimistic evaluation | walk-forward retraining, baselines on the same protocol, perfect foresight shown as ceiling |
| Data outage at 10:30 | retries, raw cache, quality gate, deterministic fallback, visible data mode |
| Model degradation / regime change | online ensemble re-weighting, adaptive conformal calibration, performance-drift alert, champion guard-rail |
| Simulated vs real numbers | the figures above come from the calibrated simulator (no internet on the build machine); with internet the same pipeline recomputes everything on real market data |
| Market design | hourly MTU and price-taker assumption — 15-min MTU, bid curves and multi-market stacking are the natural PFE extension |

## 8. Why this is a strong PFE topic
It combines **time-series ML (probabilistic, deep learning)**, **mathematical optimisation under uncertainty**, **data engineering &
MLOps** and **full-stack delivery**, on a real, growing market with a measurable € outcome. Natural extensions: intraday/XBID and
aFRR/FCR stacking, 15-minute products, degradation-aware bidding, fleet (portfolio) optimisation, integration with metering/EMS data.
