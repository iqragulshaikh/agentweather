"""Day 11: the remaining metrics, with the same folds, 24 h gap and lambda shrinkage
as Days 8-10.

  UV index (daytime rows)         Ridge / RF on the change, clipped at 0
  Wind direction                  Ridge / RF on the sin/cos change, judged by angular error
  Rain probability                logistic regression / RF classifier
  Precipitation (mm)              P(rain) x typical intensity when it rains
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.training.data import REG, folds, load

LAMBDAS = [0.0, 0.25, 0.5, 0.75, 1.0]
Path("docs/results").mkdir(parents=True, exist_ok=True)

labeled, X, feats = load()
splits = folds(len(labeled))


def rmse(a, b):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(b)) ** 2)))


def mae(a, b):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


def regressors():
    d = {f"ridge_a{a}": (lambda a=a: make_pipeline(StandardScaler(), Ridge(alpha=a)))
         for a in [10, 100, 1000, 10000]}
    d["rf"] = lambda: RandomForestRegressor(n_estimators=60, min_samples_leaf=5,
                                            max_features=0.33, n_jobs=-1, random_state=42)
    return d


def show(df, title):
    g = df[df.lam.isin([0.5, 1.0])].groupby(["model", "lam"])[["rmse", "mae"]].mean().round(3)
    print(f"\n=== {title}: mean over folds "
          f"(naive RMSE {df.naive.mean():.3f}, naive MAE {df.naive_mae.mean():.3f}) ===")
    print(g.to_string())


# ---------------------------------------------------------------- UV (daytime only)
def run_uv():
    tgt, cur = REG["uv_index"]
    y = labeled[tgt].to_numpy()
    now = labeled[cur].to_numpy()
    change = y - now
    rows = []
    for k, (tr, va) in enumerate(splits, 1):
        day = y[va] > 0                                   # score daytime hours only
        n_rmse, n_mae = rmse(y[va][day], now[va][day]), mae(y[va][day], now[va][day])
        for name, make in regressors().items():
            dp = make().fit(X.iloc[tr], change[tr]).predict(X.iloc[va])
            for lam in LAMBDAS:
                p = np.clip(now[va] + lam * dp, 0, None)
                rows.append(dict(metric="uv_index_day", fold=k, model=name, lam=lam,
                                 rmse=rmse(y[va][day], p[day]), mae=mae(y[va][day], p[day]),
                                 naive=n_rmse, naive_mae=n_mae,
                                 bias=float(np.mean(p[day] - y[va][day]))))
        print(f"UV fold {k} done")
    df = pd.DataFrame(rows)
    df.to_csv("docs/results/day11_uv.csv", index=False)
    show(df, "UV index, daytime hours")


# ---------------------------------------------------------------- wind direction
def ang_err(sin_p, cos_p, sin_t, cos_t):
    d = np.degrees(np.arctan2(sin_p, cos_p) - np.arctan2(sin_t, cos_t))
    return np.abs((d + 180) % 360 - 180)


def run_wind_dir():
    ns, nc = labeled["wind_sin"].to_numpy(), labeled["wind_cos"].to_numpy()
    ts_, tc = labeled["target_wind_sin"].to_numpy(), labeled["target_wind_cos"].to_numpy()
    change = np.column_stack([ts_ - ns, tc - nc])
    rows = []
    for k, (tr, va) in enumerate(splits, 1):
        e0 = ang_err(ns[va], nc[va], ts_[va], tc[va])
        n_rmse, n_mae = float(np.sqrt(np.mean(e0 ** 2))), float(e0.mean())
        for name, make in regressors().items():
            dp = make().fit(X.iloc[tr], change[tr]).predict(X.iloc[va])
            for lam in LAMBDAS:
                e = ang_err(ns[va] + lam * dp[:, 0], nc[va] + lam * dp[:, 1], ts_[va], tc[va])
                rows.append(dict(metric="wind_dir_deg", fold=k, model=name, lam=lam,
                                 rmse=float(np.sqrt(np.mean(e ** 2))), mae=float(e.mean()),
                                 naive=n_rmse, naive_mae=n_mae, bias=np.nan))
        print(f"Wind direction fold {k} done")
    df = pd.DataFrame(rows)
    df.to_csv("docs/results/day11_winddir.csv", index=False)
    show(df, "Wind direction, angular error in degrees")


# ---------------------------------------------------------------- rain + precipitation
def run_rain():
    y = labeled["target_rain"].astype(int).to_numpy()
    mm = labeled["target_precip_mm"].to_numpy()
    now_mm = labeled["precip_mm"].to_numpy()
    models = {
        "logreg_C0.01": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.01, max_iter=3000)),
        "logreg_C0.1": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000)),
        "logreg_C1": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=3000)),
        "rf": lambda: RandomForestClassifier(n_estimators=100, min_samples_leaf=10,
                                             max_features=0.33, n_jobs=-1, random_state=42),
    }
    rain_rows, precip_rows = [], []
    pooled = {m: ([], []) for m in models}
    for k, (tr, va) in enumerate(splits, 1):
        base = y[tr].mean()
        probs = {"const": np.full(len(va), base), "naive": (now_mm[va] >= 0.1).astype(float)}
        for name, make in models.items():
            probs[name] = make().fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[va])[:, 1]
        b_const = brier_score_loss(y[va], probs["const"])
        for name, p in probs.items():
            b = brier_score_loss(y[va], p)
            rain_rows.append(dict(fold=k, model=name, rain_rate=y[va].mean(),
                                  PR_AUC=average_precision_score(y[va], p),
                                  Brier=b, BSS=1 - b / b_const))
            if name in pooled:
                pooled[name][0].append(y[va])
                pooled[name][1].append(p)

        # precipitation in mm = P(rain) x mean intensity of rainy hours in the training rows
        inten = mm[tr][y[tr] == 1].mean()
        clim = mm[tr].mean()
        mse_clim = np.mean((mm[va] - clim) ** 2)
        fcs = {"zero": np.zeros(len(va)), "naive": now_mm[va], "climatology": np.full(len(va), clim)}
        for name in models:
            fcs[name] = probs[name] * inten
        for name, f in fcs.items():
            precip_rows.append(dict(fold=k, model=name, RMSE=rmse(mm[va], f), MAE=mae(mm[va], f),
                                    skill_vs_clim=1 - np.mean((mm[va] - f) ** 2) / mse_clim))
        print(f"Rain fold {k} done (rain rate in validation {y[va].mean():.3f})")

    rain = pd.DataFrame(rain_rows)
    rain.to_csv("docs/results/day11_rain.csv", index=False)
    precip = pd.DataFrame(precip_rows)
    precip.to_csv("docs/results/day11_precip.csv", index=False)

    print("\n=== RAIN PROBABILITY: mean over folds (higher PR_AUC/BSS is better, lower Brier is better) ===")
    g = rain.groupby("model")[["PR_AUC", "Brier", "BSS"]].mean()
    g["folds_BSS>0"] = rain.assign(w=rain["BSS"] > 0).groupby("model")["w"].sum()
    print(g.round(4).to_string())
    print("\nPR-AUC per fold:")
    print(rain.pivot(index="model", columns="fold", values="PR_AUC").round(3).to_string())
    print("\nBrier skill score vs climatology per fold (0 = no better than the base rate):")
    print(rain.pivot(index="model", columns="fold", values="BSS").round(3).to_string())

    print("\n=== PRECIPITATION (mm) = P(rain) x typical intensity: mean over folds ===")
    print("skill_vs_clim: 1 = perfect, 0 = no better than the training average, <0 = worse")
    print(precip.groupby("model")[["RMSE", "MAE", "skill_vs_clim"]].mean().round(4).to_string())

    best = g.drop(index=["const", "naive"])["Brier"].idxmin()
    obs = np.concatenate(pooled[best][0])
    pr = np.concatenate(pooled[best][1])
    print(f"\n=== CALIBRATION of '{best}' (all folds pooled): does 'x% rain' happen x% of the time? ===")
    bins = pd.cut(pr, [0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0001], include_lowest=True)
    cal = pd.DataFrame({"p": pr, "y": obs}).groupby(bins, observed=True).agg(
        hours=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean"))
    print(cal.round(3).to_string())
    cal.to_csv("docs/results/day11_rain_calibration.csv")
    print("\nAlert thresholds (pooled): flag 'rain likely' when P(rain) >= t")
    for t in [0.1, 0.2, 0.3, 0.5]:
        flag = pr >= t
        tp = int((flag & (obs == 1)).sum())
        print(f"  t={t:.1f}: flagged {int(flag.sum()):5d} h | precision "
              f"{tp / max(flag.sum(), 1):.2f} | recall {tp / max(obs.sum(), 1):.2f}")


if __name__ == "__main__":
    run_uv()
    run_wind_dir()
    run_rain()