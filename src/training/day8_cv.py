"""Day 8: naive vs Ridge vs Random Forest, expanding-window CV."""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (average_precision_score, brier_score_loss,
                             mean_absolute_error, mean_squared_error, r2_score)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.training.data import REG, clip, folds, load

TREES = 60 if "quick" in sys.argv else 150
OUT = Path("docs/results")
OUT.mkdir(parents=True, exist_ok=True)


def make_reg(name):
    if name == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    return RandomForestRegressor(n_estimators=TREES, min_samples_leaf=5,
                                 max_features=0.33, n_jobs=-1, random_state=42)


def score(y, p):
    return dict(RMSE=mean_squared_error(y, p) ** 0.5,
                MAE=mean_absolute_error(y, p), R2=r2_score(y, p))


def ang_err(sin_p, cos_p, sin_t, cos_t):
    d = np.degrees(np.arctan2(sin_p, cos_p)) - np.degrees(np.arctan2(sin_t, cos_t))
    return np.abs((d + 180) % 360 - 180)


labeled, X, feats = load()
print(f"{len(labeled)} rows, {len(feats)} features")
splits = folds(len(labeled))
reg_rows, rain_rows = [], []
t_start = time.time()

for k, (tr, va) in enumerate(splits, 1):
    a, b = labeled.loc[va[0], "ts"], labeled.loc[va[-1], "ts"]
    print(f"\nfold {k}: train {len(tr)} rows | validate {a:%Y-%m-%d} -> {b:%Y-%m-%d} "
          f"| rain rate {labeled.loc[va, 'target_rain'].mean():.3f}")
    store = {m: {} for m in ["naive", "ridge", "rf"]}

    for name, (tgt, cur) in REG.items():
        y = labeled[tgt].to_numpy()
        now = labeled[cur].to_numpy()
        store["naive"][name] = now[va]
        for m in ["ridge", "rf"]:
            model = make_reg(m)
            if name == "precip_mm":                       # direct, mostly zeros
                model.fit(X.iloc[tr], y[tr])
                p = model.predict(X.iloc[va])
            else:                                         # learn the change from now
                model.fit(X.iloc[tr], y[tr] - now[tr])
                p = now[va] + model.predict(X.iloc[va])
            store[m][name] = clip(name, p)
        for m in store:
            reg_rows.append(dict(fold=k, model=m, metric=name,
                                 **score(y[va], store[m][name])))
        if name == "uv_index":                            # daytime only
            day = y[va] > 0
            for m in store:
                reg_rows.append(dict(fold=k, model=m, metric="uv_index_day",
                                     **score(y[va][day], store[m][name][day])))

    # wind direction: angular error in degrees
    for m in store:
        e = ang_err(store[m]["wind_sin"], store[m]["wind_cos"],
                    labeled["target_wind_sin"].to_numpy()[va],
                    labeled["target_wind_cos"].to_numpy()[va])
        reg_rows.append(dict(fold=k, model=m, metric="wind_dir_deg",
                             RMSE=np.sqrt((e ** 2).mean()), MAE=e.mean(), R2=np.nan))

    # rain probability (classification)
    y = labeled["target_rain"].astype(int).to_numpy()
    if y[va].sum() == 0 or y[tr].sum() == 0:
        print("  rain: no positives in train or validation, skipped")
    else:
        probs = {
            "const": np.full(len(va), y[tr].mean()),
            "naive": (labeled["precip_mm"].to_numpy()[va] >= 0.1).astype(float),
        }
        lr = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000))
        lr.fit(X.iloc[tr], y[tr])
        probs["logreg"] = lr.predict_proba(X.iloc[va])[:, 1]
        rf = RandomForestClassifier(n_estimators=TREES, min_samples_leaf=5,
                                    max_features=0.33, n_jobs=-1, random_state=42)
        rf.fit(X.iloc[tr], y[tr])
        probs["rf"] = rf.predict_proba(X.iloc[va])[:, 1]
        for m, p in probs.items():
            rain_rows.append(dict(fold=k, model=m,
                                  PR_AUC=average_precision_score(y[va], p),
                                  Brier=brier_score_loss(y[va], p)))
    print(f"  done ({(time.time() - t_start) / 60:.1f} min so far)")

reg = pd.DataFrame(reg_rows)
rain = pd.DataFrame(rain_rows)
reg.to_csv(OUT / "day8_regression_folds.csv", index=False)
rain.to_csv(OUT / "day8_rain_folds.csv", index=False)

print("\n=== MEAN OVER FOLDS (lower RMSE/MAE is better) ===")
print(reg.groupby(["metric", "model"])[["RMSE", "MAE", "R2"]].mean().round(3).to_string())

rm = reg.pivot_table(index=["metric", "fold"], columns="model", values="RMSE")
imp = (1 - rm[["ridge", "rf"]].div(rm["naive"], axis=0)) * 100
for m in ["ridge", "rf"]:
    print(f"\n=== {m}: RMSE improvement over naive (%), per fold ===")
    print(imp[m].unstack("fold").round(1).to_string())

print("\n=== RAIN (higher PR_AUC is better, lower Brier is better) ===")
print(rain.groupby("model")[["PR_AUC", "Brier"]].mean().round(4).to_string())
print(rain.pivot_table(index="fold", columns="model", values="PR_AUC").round(3).to_string())
print(f"\ntotal time: {(time.time() - t_start) / 60:.1f} min")