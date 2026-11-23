"""Compare all model families and run the honest leave-one-fold-out selection.
Reads every candidate file that exists (Day 8b: ridge/rf, Day 9: sarimax, ...)."""
from pathlib import Path

import pandas as pd

FILES = ["docs/results/day8b_diagnose.csv", "docs/results/day9_sarimax.csv",
         "docs/results/day9b_sarimax_rolling.csv", "docs/results/day10_lstm.csv"]
res = pd.concat([pd.read_csv(f) for f in FILES if Path(f).exists()], ignore_index=True)
print("candidate files used:", [f for f in FILES if Path(f).exists()])

res["family"] = res["model"].str.replace(r"_a\d+$", "", regex=True)   # ridge_a1000 -> ridge
res["cand"] = res["model"] + "|lam=" + res["lam"].astype(str)

# 1) best fixed setting per family (tuned on all folds, so slightly optimistic)
m = res.groupby(["metric", "family", "model", "lam"])["rmse"].mean().reset_index()
best = m.loc[m.groupby(["metric", "family"])["rmse"].idxmin()]
fam = best.pivot(index="metric", columns="family", values="rmse")
fam["naive"] = res.groupby("metric")["naive"].mean()
print("\n=== Best setting per family: mean RMSE over folds (optimistic) ===")
print(fam.round(3).to_string())

# 2) honest: choose on 4 folds, score on the 5th
rows = []
for metric, g in res.groupby("metric"):
    piv = g.pivot_table(index="fold", columns="cand", values="rmse")
    naive = g.groupby("fold")["naive"].first()
    for k in piv.index:
        pick = piv[piv.index != k].mean().idxmin()
        rows.append(dict(metric=metric, fold=k, chosen=pick, rmse=piv.loc[k, pick], naive=naive[k]))
out = pd.DataFrame(rows)
s = out.groupby("metric").agg(naive=("naive", "mean"), selected=("rmse", "mean"))
s["improvement_pct"] = (1 - s["selected"] / s["naive"]) * 100
s["folds_better"] = out.assign(w=out["rmse"] < out["naive"]).groupby("metric")["w"].sum()
print("\n=== Leave-one-fold-out selection over ALL families (honest) ===")
print(s.round(3).to_string())
print("\n=== What was chosen per held-out fold ===")
print(out.pivot(index="metric", columns="fold", values="chosen").to_string())