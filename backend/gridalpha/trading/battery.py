"""Battery (BESS) day-ahead dispatch as a mixed-integer linear program.

    max  sum_t p_t (d_t - c_t) dt  -  k_deg * sum_t d_t dt
    s.t. s_t = s_{t-1} + eta_c c_t dt - d_t dt / eta_d     (state of charge)
         0 <= c_t, d_t <= P,  E_min <= s_t <= E_max
         c_t <= P u_t,  d_t <= P (1 - u_t),  u_t in {0,1}   (no simultaneous c/d)
         sum_t d_t dt <= cycles * E                          (warranty cycles)
         s_T >= s_0                                          (energy-neutral day)

Risk-aware variant (stochastic, Rockafellar-Uryasev CVaR):
one non-anticipative schedule is evaluated on S correlated price scenarios
and we minimise  (1 - lambda) * E[-profit] + lambda * CVaR_alpha[-profit].
Solved with HiGHS through scipy.optimize.milp — typically < 30 ms.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix, lil_matrix


@dataclass(frozen=True)
class BatterySpec:
    power_mw: float = 10.0
    energy_mwh: float = 20.0
    rte: float = 0.88
    max_cycles_per_day: float = 1.5
    soc_min_frac: float = 0.05
    soc_max_frac: float = 0.95
    soc_init_frac: float = 0.5
    degradation_eur_per_mwh: float = 8.0

    @property
    def eta(self) -> float:
        return float(np.sqrt(self.rte))

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DispatchResult:
    charge: np.ndarray
    discharge: np.ndarray
    soc: np.ndarray
    expected_pnl: float
    status: str
    solve_ms: float
    scenario_pnl: np.ndarray | None = None

    @property
    def net(self) -> np.ndarray:
        return self.discharge - self.charge

    def risk(self, alpha: float = 0.95) -> dict:
        if self.scenario_pnl is None or len(self.scenario_pnl) == 0:
            return {}
        s = np.sort(self.scenario_pnl)
        k = max(1, int(np.ceil((1 - alpha) * len(s))))
        return {
            "p5": float(np.percentile(s, 5)),
            "p50": float(np.percentile(s, 50)),
            "p95": float(np.percentile(s, 95)),
            "cvar": float(s[:k].mean()),
            "prob_loss": float(np.mean(s < 0)),
        }


def optimise(
    spec: BatterySpec,
    prices: np.ndarray,
    scenarios: np.ndarray | None = None,
    risk_aversion: float = 0.0,
    alpha: float = 0.95,
    dt: float = 1.0,
) -> DispatchResult:
    """Deterministic (scenarios=None) or mean-CVaR dispatch for one day."""
    import time

    t0 = time.perf_counter()
    p = np.asarray(prices, dtype=float)
    T = len(p)
    use_scen = scenarios is not None
    use_cvar = use_scen and risk_aversion > 0
    S = scenarios.shape[0] if use_cvar else 0
    lam = float(np.clip(risk_aversion, 0, 1)) if use_cvar else 0.0
    P, E = spec.power_mw, spec.energy_mwh
    eta, k = spec.eta, spec.degradation_eur_per_mwh
    s0 = spec.soc_init_frac * E

    ic, id_, is_, iu = 0, T, 2 * T, 3 * T
    ieta, iz = 4 * T, 4 * T + 1
    n = 4 * T + (1 + S if use_cvar else 0)

    # ---- objective (minimise cost) --------------------------------------------
    # with scenarios we maximise the *expected* profit (mean scenario price),
    # which differs from the median forecast when the distribution is skewed
    pbar = scenarios.mean(axis=0) if use_scen else p
    cobj = np.zeros(n)
    w = 1 - lam
    cobj[ic:ic + T] = w * pbar * dt
    cobj[id_:id_ + T] = w * (-pbar * dt + k * dt)
    if use_cvar:
        cobj[ieta] = lam
        cobj[iz:iz + S] = lam / ((1 - alpha) * S)

    lo, hi = [], []
    A = lil_matrix((T + 1 + 2 * T + S, n))
    r = 0
    # SoC dynamics
    for t in range(T):
        A[r, is_ + t] = 1.0
        if t > 0:
            A[r, is_ + t - 1] = -1.0
        A[r, ic + t] = -eta * dt
        A[r, id_ + t] = dt / eta
        rhs = s0 if t == 0 else 0.0
        lo.append(rhs)
        hi.append(rhs)
        r += 1
    # cycle / throughput limit
    A[r, id_:id_ + T] = dt
    lo.append(-np.inf)
    hi.append(spec.max_cycles_per_day * E)
    r += 1
    # mutual exclusivity charge/discharge
    for t in range(T):
        A[r, ic + t] = 1.0
        A[r, iu + t] = -P
        lo.append(-np.inf)
        hi.append(0.0)
        r += 1
        A[r, id_ + t] = 1.0
        A[r, iu + t] = P
        lo.append(-np.inf)
        hi.append(P)
        r += 1
    # CVaR epigraph: loss_s - eta - z_s <= 0
    for s in range(S):
        ps = scenarios[s]
        for t in range(T):
            A[r, ic + t] = ps[t] * dt
            A[r, id_ + t] = -ps[t] * dt + k * dt
        A[r, ieta] = -1.0
        A[r, iz + s] = -1.0
        lo.append(-np.inf)
        hi.append(0.0)
        r += 1
    cons = LinearConstraint(csr_matrix(A[:r]), np.array(lo), np.array(hi))

    lb = np.zeros(n)
    ub = np.full(n, np.inf)
    ub[ic:ic + T] = P
    ub[id_:id_ + T] = P
    lb[is_:is_ + T] = spec.soc_min_frac * E
    ub[is_:is_ + T] = spec.soc_max_frac * E
    lb[is_ + T - 1] = max(s0, spec.soc_min_frac * E)
    ub[iu:iu + T] = 1
    if use_cvar:
        lb[ieta], ub[ieta] = -np.inf, np.inf
    integrality = np.zeros(n)
    integrality[iu:iu + T] = 1

    res = milp(cobj, constraints=cons, integrality=integrality, bounds=Bounds(lb, ub),
               options={"time_limit": 10.0, "mip_rel_gap": 1e-4})
    ms = (time.perf_counter() - t0) * 1000
    if res.x is None:  # infeasible / timeout -> stay idle (safe fallback)
        z = np.zeros(T)
        return DispatchResult(z, z, np.full(T, s0), 0.0, f"fallback:{res.message}", ms)

    x = res.x
    c = np.clip(x[ic:ic + T], 0, None)
    d = np.clip(x[id_:id_ + T], 0, None)
    soc = x[is_:is_ + T]
    exp_pnl = settle(pbar, c, d, spec, dt)
    scen_pnl = None
    if scenarios is not None:
        scen_pnl = (scenarios * (d - c) * dt).sum(axis=1) - k * d.sum() * dt
    return DispatchResult(c, d, soc, exp_pnl, "optimal", ms, scen_pnl)


def settle(prices: np.ndarray, charge: np.ndarray, discharge: np.ndarray,
           spec: BatterySpec, dt: float = 1.0) -> float:
    """Realised P&L of a committed schedule at day-ahead clearing prices."""
    p = np.asarray(prices, dtype=float)
    return float((p * (discharge - charge)).sum() * dt
                 - spec.degradation_eur_per_mwh * discharge.sum() * dt)
