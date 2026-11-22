"""Day 9b: SARIMAX refitted every 7 days on the last 60 days (mimics daily retraining)."""
import time

import numpy as np
import pandas as pd

from src.training.data import REG, folds, load
from src.training.day9_sarimax import LAMBDAS, METRICS, design, fit_forecast, rmse

WINDOW = 24 * 60     # training window: the last 60 days
STEP = 24 * 7        # refit every 7 days
GAP = 24             # same information cut-off as the other models

labeled, _, _ = load()
hours = labeled["ts"].dt.hour.to_numpy()
X = design(hours)
splits = folds(len(labeled))
rows, t0 = [], time.time()

for name in METRICS:
    tgt, cur = REG[name]
    y = labeled[tgt].to_numpy()
    s = labeled[cur].to_numpy()
    for k, (_, va) in enumerate(splits, 1):
        fc = np.empty(len(va))
        for i in range(0, len(va), STEP):
            chunk = va[i:i + STEP]
            end = chunk[0] - GAP                       # only data older than the gap
            tr = np.arange(end - WINDOW, end)
            fc[i:i + len(chunk)], phi = fit_forecast(s, X, tr, chunk)
        now = s[va]
        naive = rmse(y[va], now)
        for lam in LAMBDAS:
            p = now + lam * (fc - now)
            rows.append(dict(metric=name, fold=k, model="sarimax_roll", lam=lam,
                             rmse=rmse(y[va], p), naive=naive,
                             bias=float(np.mean(p - y[va]))))
        print(f"{name} fold {k}: last AR={np.round(phi, 3)} | RMSE full model "
              f"{rmse(y[va], fc):.3f} vs naive {naive:.3f} ({(time.time() - t0) / 60:.1f} min)")

res = pd.DataFrame(rows)
res.to_csv("docs/results/day9b_sarimax_rolling.csv", index=False)
print("\n=== Rolling SARIMAX mean RMSE over folds (lam=0 is the naive baseline) ===")
print(res.pivot_table(index="metric", columns="lam", values="rmse").round(3).to_string())