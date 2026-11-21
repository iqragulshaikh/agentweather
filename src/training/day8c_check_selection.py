"""Day 8c: honest check. Pick (model, lam) on 4 folds, score it on the 5th."""
import pandas as pd

res = pd.read_csv("docs/results/day8b_diagnose.csv")
res["cand"] = res["model"] + "|lam=" + res["lam"].astype(str)

rows = []
for metric, g in res.groupby("metric"):
    piv = g.pivot_table(index="fold", columns="cand", values="rmse")   # folds x candidates
    naive = g.groupby("fold")["naive"].first()
    for k in piv.index:
        best = piv[piv.index != k].mean().idxmin()                     # chosen WITHOUT fold k
        rows.append(dict(metric=metric, fold=k, chosen=best,
                         rmse=piv.loc[k, best], naive=naive[k]))

out = pd.DataFrame(rows)
summary = out.groupby("metric").agg(naive=("naive", "mean"), selected=("rmse", "mean"))
summary["improvement_pct"] = (1 - summary["selected"] / summary["naive"]) * 100
summary["folds_better_than_naive"] = out.assign(w=out["rmse"] < out["naive"]).groupby("metric")["w"].sum()

print("=== Leave-one-fold-out selection (the gain you can honestly expect) ===")
print(summary.round(3).to_string())
print("\n=== What was chosen when each fold was held out ===")
print(out.pivot(index="metric", columns="fold", values="chosen").to_string())
print("\n=== RMSE per held-out fold: selected vs naive ===")
print(out.pivot(index="metric", columns="fold", values="rmse").round(2).to_string())
print(out.pivot(index="metric", columns="fold", values="naive").round(2).to_string())