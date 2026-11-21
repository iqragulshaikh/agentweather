from datetime import date, timedelta

import pandas as pd

from src.features.build_features import build_features
from src.features.impute import impute
from src.features.targets import build_targets
from src.ingestion.history import fetch_history

end = date.today() - timedelta(days=2)
start = end - timedelta(days=365)
raw = fetch_history(start, end)

clean, report = impute(raw)
feats = build_features(clean)
targets = build_targets(clean)

print("\nreport:", report)
print("range:", clean["timestamp"].min(), "->", clean["timestamp"].max())
print("features:", feats.shape, "| targets:", targets.shape)

c = clean.set_index("timestamp")
t = targets.set_index("timestamp")
ts = t.index[500]
assert t.loc[ts, "target_temp_c"] == c.loc[ts + pd.Timedelta("24h"), "temp_c"]
print("target check passed")

t["month"] = t.index.strftime("%Y-%m")
print("\nRain rate per month (share of hours with rain at t+24):")
print(t.groupby("month")["target_rain"].mean().round(3))
print("\nTotal rain hours:", int(t["target_rain"].sum()), "of", len(t))
print(targets.describe().T[["min", "mean", "max"]])