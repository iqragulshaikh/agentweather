"""Day 9: statistical family. SARIMAX = daily Fourier terms (exog) + AR(2) errors.

Forecast for row t = value at t+24 using only information up to t, the same
protocol as the Ridge/RF models, so the results are directly comparable.
"""
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX

from src.training.data import REG, folds, load

METRICS = ["aqi", "temp_c", "humidity", "wind_speed_ms"]
K = 4                                   # daily harmonics
P = 2                                   # AR order of the errors
H = 24                                  # forecast horizon (hours)
LAMBDAS = [0.0, 0.25, 0.5, 0.75, 1.0]   # 0 = naive baseline, 1 = full model
Path("docs/results").mkdir(parents=True, exist_ok=True)
warnings.filterwarnings("ignore")


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def design(hours):
    """Constant + K daily sin/cos pairs. Target hour-of-day == origin hour-of-day
    (24 h shift), so one design matrix serves both."""
    cols = [np.ones(len(hours))]
    for k in range(1, K + 1):
        cols += [np.sin(2 * np.pi * k * hours / 24), np.cos(2 * np.pi * k * hours / 24)]
    return np.column_stack(cols)


def fit_forecast(s, X, tr, va):
    """Fit on training rows, then 24-step-ahead forecast from every origin in va."""
    res = SARIMAX(s[tr], exog=X[tr], order=(P, 0, 0), trend="n").fit(disp=False, maxiter=200)
    nx = X.shape[1]                                 # params order: exog betas, AR, sigma2
    beta = np.asarray(res.params[:nx])
    phi = np.asarray(res.params[nx:nx + P])

    eta = s - X @ beta                              # profile-free residuals (known at origin)
    e = [eta[va - j] for j in range(P)]             # e[0]=eta_t, e[1]=eta_{t-1}
    for _ in range(H):                              # AR recursion, all origins at once
        e = [sum(phi[j] * e[j] for j in range(P))] + e[:-1]
    return X[va] @ beta + e[0], phi


if __name__ == "__main__":
    labeled, _, _ = load()
    hours = labeled["ts"].dt.hour.to_numpy()
    X = design(hours)
    splits = folds(len(labeled))
    rows, t0 = [], time.time()

    for name in METRICS:
        tgt, cur = REG[name]
        y = labeled[tgt].to_numpy()
        s = labeled[cur].to_numpy()                 # observed series at each hour
        for k, (tr, va) in enumerate(splits, 1):
            fc, phi = fit_forecast(s, X, tr, va)
            now = s[va]
            naive = rmse(y[va], now)
            for lam in LAMBDAS:
                p = now + lam * (fc - now)
                rows.append(dict(metric=name, fold=k, model="sarimax", lam=lam,
                                 rmse=rmse(y[va], p), naive=naive,
                                 bias=float(np.mean(p - y[va]))))
            print(f"{name} fold {k}: AR={np.round(phi, 3)} | RMSE full model "
                  f"{rmse(y[va], fc):.3f} vs naive {naive:.3f} "
                  f"({(time.time() - t0) / 60:.1f} min)")

    res = pd.DataFrame(rows)
    res.to_csv("docs/results/day9_sarimax.csv", index=False)
    print("\n=== SARIMAX mean RMSE over folds (lam=0 is the naive baseline) ===")
    print(res.pivot_table(index="metric", columns="lam", values="rmse").round(3).to_string())
    