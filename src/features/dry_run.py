from src.features.build_features import build_features
from src.features.impute import impute
from src.features.targets import build_targets
from src.ingestion.fuse import fuse

raw = fuse(past_days=92)
raw = raw.drop(columns=[c for c in raw.columns if c.startswith("ow_")])
clean, report = impute(raw)
feats = build_features(clean)
targets = build_targets(clean)

print("report:", report)
print("features:", feats.shape, "| targets:", targets.shape)
print("range:", clean["timestamp"].min(), "->", clean["timestamp"].max())

# leakage check: target at row t must equal the real value at t+24h
c = clean.set_index("timestamp")
t = targets.set_index("timestamp")
ts = t.index[200]
assert t.loc[ts, "target_temp_c"] == c.loc[ts + __import__("pandas").Timedelta("24h"), "temp_c"]
print("target check passed")

print("\nRain rate (share of hours with rain at t+24):", round(targets["target_rain"].mean(), 4))
print(targets.describe().T[["min", "mean", "max"]])