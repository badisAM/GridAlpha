"""TiDE — Time-series Dense Encoder (Das et al., Google Research, TMLR 2023),
re-implemented compactly in PyTorch for day-ahead price *quantiles*.

Why TiDE rather than an LSTM/Transformer?
* it natively consumes known-future covariates (weather forecasts, residual
  load proxies) for all 24 target hours — exactly the day-ahead setting;
* it is MLP-only: trains in seconds on a laptop CPU and is competitive with
  Transformer models on long-horizon benchmarks at a fraction of the cost.

Design: RevIN-style instance normalisation of the 7-day price lookback,
direct multi-horizon decoding (24 h at once), monotone quantile head
(q10 <= q50 <= q90 by construction), pinball loss, early stopping on a
time-ordered validation split, small seed ensemble.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import get_settings
from ..features.builder import TIDE_FUTURE, TIDE_STATIC_NUM
from ..log import get_logger
from .base import QCOLS, Forecaster

log = get_logger("tide")

try:  # torch is optional at import time so the API can run without it
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    TORCH_OK = True
except Exception:  # pragma: no cover
    TORCH_OK = False

LOOKBACK_DAYS = 7
H = 24
QUANTILES = (0.1, 0.5, 0.9)


# --------------------------------------------------------------------------- data
class DayTensors:
    """Day-level view of the hourly feature table (robust to DST days)."""

    def __init__(self, feat: pd.DataFrame) -> None:
        days = pd.date_range(feat["delivery_date"].min(), feat["delivery_date"].max(), freq="D")
        self.days = days

        def piv(col: str) -> np.ndarray:
            t = feat.pivot_table(index="delivery_date", columns="hour", values=col, aggfunc="mean")
            t = t.reindex(index=days, columns=range(H))
            t = t.interpolate(axis=1, limit_direction="both")
            return t.to_numpy(dtype="float32")

        self.price = piv("price")                                    # D x 24
        self.fut = np.stack([piv(c) for c in TIDE_FUTURE], axis=-1)  # D x 24 x F
        first = feat.groupby("delivery_date")[TIDE_STATIC_NUM].first().reindex(days)
        dow = np.eye(7, dtype="float32")[days.dayofweek.to_numpy()]
        self.static_num = first.to_numpy(dtype="float32")
        self.dow = dow
        self.pos = {d: i for i, d in enumerate(days)}

    def sample(self, day: pd.Timestamp):
        i = self.pos.get(pd.Timestamp(day))
        if i is None or i < LOOKBACK_DAYS:
            return None
        lb = self.price[i - LOOKBACK_DAYS:i].reshape(-1)
        if not np.isfinite(lb).all():
            return None
        return lb, self.fut[i], self.static_num[i], self.dow[i], self.price[i]


if TORCH_OK:

    class _ResBlock(nn.Module):
        def __init__(self, i: int, h: int, o: int, p: float) -> None:
            super().__init__()
            self.lin = nn.Sequential(nn.Linear(i, h), nn.ReLU(), nn.Linear(h, o), nn.Dropout(p))
            self.skip = nn.Linear(i, o)
            self.norm = nn.LayerNorm(o)

        def forward(self, x):
            return self.norm(self.lin(x) + self.skip(x))

    class TiDENet(nn.Module):
        def __init__(self, n_fut: int, n_static: int, proj: int = 32, hid: int = 256,
                     dec: int = 32, p: float = 0.3) -> None:
            super().__init__()
            L = LOOKBACK_DAYS * H
            self.proj = _ResBlock(n_fut, 32, proj, p)
            self.enc = nn.Sequential(
                _ResBlock(L + H * proj + n_static, hid, hid, p), _ResBlock(hid, hid, hid, p)
            )
            self.dec = _ResBlock(hid, hid, H * dec, p)
            self.temporal = _ResBlock(dec + proj, 32, 3, p)
            self.lin_skip = nn.Linear(L, H)
            self.dec_dim = dec

        def forward(self, lb, fut, st):
            B = lb.shape[0]
            pf = self.proj(fut)
            e = self.enc(torch.cat([lb, pf.reshape(B, -1), st], dim=1))
            d = self.dec(e).reshape(B, H, self.dec_dim)
            o = self.temporal(torch.cat([d, pf], dim=-1))
            med = o[..., 1] + self.lin_skip(lb)
            lo = med - F.softplus(o[..., 0]) - 1e-3
            hi = med + F.softplus(o[..., 2]) + 1e-3
            return torch.stack([lo, med, hi], dim=-1)

    def _pinball_loss(pred, y):
        loss = 0.0
        for k, q in enumerate(QUANTILES):
            d = y - pred[..., k]
            loss = loss + torch.maximum(q * d, (q - 1) * d).mean()
        return loss / len(QUANTILES)


# --------------------------------------------------------------------------- model
class TiDEQuantile(Forecaster):
    name = "tide"
    family = "deep_learning"

    def __init__(self, epochs: int | None = None, seeds: int | None = None,
                 warm_start: bool = True, finetune_epochs: int = 30) -> None:
        s = get_settings()
        self.epochs = epochs or s.tide_epochs
        self.warm_start = warm_start
        self.finetune_epochs = finetune_epochs
        self.n_seeds = seeds or s.tide_seeds
        self.nets: list = []
        self.stats: dict = {}
        self.history: list[dict] = []

    # -- normalisation -------------------------------------------------------
    @staticmethod
    def _revin(lb: np.ndarray):
        mu = lb.mean(axis=1, keepdims=True)
        sd = np.maximum(lb.std(axis=1, keepdims=True), 5.0)
        return mu, sd

    def _assemble(self, samples: list, fit_stats: bool):
        lb = np.stack([s[0] for s in samples])
        fut = np.stack([s[1] for s in samples])
        stn = np.stack([s[2] for s in samples])
        dow = np.stack([s[3] for s in samples])
        y = np.stack([s[4] for s in samples])
        mu, sd = self._revin(lb)
        if fit_stats:
            self.stats = {
                "fut_mu": np.nanmean(fut, axis=(0, 1)).tolist(),
                "fut_sd": (np.nanstd(fut, axis=(0, 1)) + 1e-6).tolist(),
                "st_mu": np.nanmean(stn, axis=0).tolist(),
                "st_sd": (np.nanstd(stn, axis=0) + 1e-6).tolist(),
            }
        fut_n = (fut - np.array(self.stats["fut_mu"])) / np.array(self.stats["fut_sd"])
        stn_n = (stn - np.array(self.stats["st_mu"])) / np.array(self.stats["st_sd"])
        static = np.concatenate([stn_n, dow, mu / 100.0, np.log(sd)], axis=1)
        arrs = [(lb - mu) / sd, fut_n, static, (y - mu) / sd]
        arrs = [np.nan_to_num(a.astype("float32"), nan=0.0, posinf=0.0, neginf=0.0) for a in arrs]
        return (*arrs, mu, sd)

    # -- training --------------------------------------------------------------
    def fit(self, feat: pd.DataFrame, before: pd.Timestamp) -> TiDEQuantile:
        if not TORCH_OK:
            raise RuntimeError("PyTorch is not installed — `pip install torch`")
        dt = DayTensors(feat)
        days = [d for d in dt.days if d < pd.Timestamp(before)]
        samples = [s for d in days if (s := dt.sample(d)) is not None and np.isfinite(s[4]).all()]
        lb, fut, st, y, _, _ = self._assemble(samples, fit_stats=True)
        n = len(lb)
        n_val = max(28, int(0.1 * n))
        idx_tr, idx_va = np.arange(n - n_val), np.arange(n - n_val, n)
        torch.set_num_threads(max(1, min(4, (torch.get_num_threads() or 1))))
        T = lambda a: torch.from_numpy(a)  # noqa: E731
        Xtr = [T(a[idx_tr]) for a in (lb, fut, st, y)]
        Xva = [T(a[idx_va]) for a in (lb, fut, st, y)]
        warm = bool(self.nets) and self.warm_start
        base_seed = get_settings().seed
        nets, history = [], []
        for k in range(self.n_seeds):
            torch.manual_seed(base_seed + k)
            if warm and k < len(self.nets):
                net = self.nets[k]          # incremental fine-tuning of last block's model
                max_epochs, lr, max_patience = self.finetune_epochs, 7e-4, 8
            else:
                net = TiDENet(fut.shape[-1], st.shape[-1])
                max_epochs, lr, max_patience = self.epochs, 2e-3, 15
            opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
            sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max_epochs)
            net.eval()
            with torch.no_grad():
                best = float(_pinball_loss(net(*Xva[:3]), Xva[3])) if warm else np.inf
            best_state = {kk: v.clone() for kk, v in net.state_dict().items()}
            patience, n_epochs = 0, 0
            g = torch.Generator().manual_seed(base_seed + k)
            for _ in range(max_epochs):
                n_epochs += 1
                net.train()
                perm = torch.randperm(len(idx_tr), generator=g)
                for b in range(0, len(perm), 64):
                    j = perm[b:b + 64]
                    opt.zero_grad()
                    loss = _pinball_loss(net(Xtr[0][j], Xtr[1][j], Xtr[2][j]), Xtr[3][j])
                    loss.backward()
                    nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                    opt.step()
                sched.step()
                net.eval()
                with torch.no_grad():
                    vl = float(_pinball_loss(net(*Xva[:3]), Xva[3]))
                if vl < best - 1e-4:
                    best, patience = vl, 0
                    best_state = {kk: v.clone() for kk, v in net.state_dict().items()}
                else:
                    patience += 1
                    if patience >= max_patience:
                        break
            net.load_state_dict(best_state)
            net.eval()
            nets.append(net)
            history.append({"seed": base_seed + k, "epochs": n_epochs, "warm_start": warm,
                            "val_pinball_norm": round(best, 4)})
        self.nets, self.history = nets, history
        log.info("TiDE trained on %d days: %s", n, self.history)
        self._n_fut, self._n_static = fut.shape[-1], st.shape[-1]
        return self

    # -- inference ----------------------------------------------------------------
    def predict(self, feat: pd.DataFrame, days: list[pd.Timestamp]) -> pd.DataFrame:
        dt = DayTensors(feat)
        out = []
        for d in days:
            s = dt.sample(d)
            rows = feat[feat["delivery_date"] == pd.Timestamp(d)]
            if s is None or rows.empty:
                continue
            s = (*s[:4], np.zeros(H, dtype="float32"))
            lb, fut, st, _, mu, sd = self._assemble([s], fit_stats=False)
            with torch.no_grad():
                preds = np.mean(
                    [net(torch.from_numpy(lb), torch.from_numpy(fut), torch.from_numpy(st)).numpy()
                     for net in self.nets], axis=0,
                )[0]
            q = preds * sd[0, 0] + mu[0, 0]  # 24 x 3
            hrs = rows["hour"].to_numpy()
            out.append(pd.DataFrame(q[hrs], index=rows.index, columns=QCOLS))
        if not out:
            return pd.DataFrame(columns=QCOLS)
        return self.monotone(pd.concat(out))

    # -- persistence ------------------------------------------------------------
    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        for k, net in enumerate(self.nets):
            torch.save(net.state_dict(), path / f"tide_seed{k}.pt")
        (path / "tide_meta.json").write_text(json.dumps({
            "stats": self.stats, "history": self.history,
            "n_fut": self._n_fut, "n_static": self._n_static, "n_seeds": len(self.nets),
        }))

    @classmethod
    def load(cls, path: Path) -> TiDEQuantile:
        meta = json.loads((path / "tide_meta.json").read_text())
        m = cls()
        m.stats, m.history = meta["stats"], meta["history"]
        m._n_fut, m._n_static = meta["n_fut"], meta["n_static"]
        m.nets = []
        for k in range(meta["n_seeds"]):
            net = TiDENet(m._n_fut, m._n_static)
            net.load_state_dict(torch.load(path / f"tide_seed{k}.pt", map_location="cpu", weights_only=True))
            net.eval()
            m.nets.append(net)
        return m
