"""Day 8b: why do Ridge/RF lose to naive on some metrics? Three quick experiments."""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.training.data import REG, folds, load

METRICS = ["aqi", "temp_c", "humidity", "wind_speed_ms"]
ALPHAS = [10, 100, 1000, 10000, 100000]
LAMBDAS = [0.0, 0.25, 0.5, 0.75, 1.0]
Path("docs/results").mkdir(parents=True, exist_ok=True)


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def make_ridge(alpha):
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha))


def make_rf():
    return RandomForestRegressor(n_estimators=60, min_samples_leaf=5,
                                 max_features=0.33, n_jobs=-1, random_state=42)


labeled, X, feats = load()
splits = folds(len(labeled))
rows = []

for name in METRICS:
    tgt, cur = REG[name]
    y = labeled[tgt].to_numpy()
    now = labeled[cur].to_numpy()
    change = y - now                       # what the models learn
    for k, (tr, va) in enumerate(splits, 1):
        naive = rmse(y[va], now[va])
        models = {f"ridge_a{a}": make_ridge(a) for a in ALPHAS}
        models["rf"] = make_rf()
        for mname, model in models.items():
            model.fit(X.iloc[tr], change[tr])
            dp = model.predict(X.iloc[va])          # predicted change
            for lam in LAMBDAS:
                p = now[va] + lam * dp              # lam=0 is the naive baseline
                rows.append(dict(metric=name, fold=k, model=mname, lam=lam,
                                 rmse=rmse(y[va], p), naive=naive,
                                 bias=float(np.mean(p - y[va]))))
    print(f"{name} done")

res = pd.DataFrame(rows)
res.to_csv("docs/results/day8b_diagnose.csv", index=False)

print("\n=== A) BIAS per fold (mean of prediction - truth), lam=1 ===")
print("Large bias = a systematic seasonal drift learned from the training window.")
a = res[(res.lam == 1.0) & res.model.isin(["ridge_a10", "rf"])]
print(a.pivot_table(index=["metric", "model"], columns="fold", values="bias").round(2).to_string())

print("\n=== B) Ridge strength: mean RMSE over folds, lam=1 (naive for reference) ===")
b = res[(res.lam == 1.0) & res.model.str.startswith("ridge")]
tb = b.pivot_table(index="metric", columns="model", values="rmse")
tb["naive"] = res.groupby("metric")["naive"].mean()
print(tb.round(3).to_string())

print("\n=== C) Shrinking the predicted change: mean RMSE over folds ===")
print("lam=0 is the naive baseline, lam=1 is the full model.")
c = res[res.model.isin(["ridge_a1000", "ridge_a10000", "ridge_a100000", "rf"])]
print(c.pivot_table(index=["metric", "model"], columns="lam", values="rmse").round(3).to_string())