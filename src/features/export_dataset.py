from pathlib import Path

import pandas as pd

from src.features.hops import get_fs

fs = get_fs()
feats = fs.get_feature_group("weather_features", version=2).read()
targets = fs.get_feature_group("weather_targets", version=2).read()

# left join keeps the newest 24 rows (no target yet)
df = feats.merge(targets, on="ts", how="left").sort_values("ts").reset_index(drop=True)
df["ts"] = pd.to_datetime(df["ts"], utc=True)

Path("data").mkdir(exist_ok=True)
df.to_parquet("data/dataset.parquet", index=False)
print("saved", df.shape, "| rows with target:", df["target_temp_c"].notna().sum())