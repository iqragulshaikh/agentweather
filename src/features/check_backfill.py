import pandas as pd

from src.features.hops import get_fs

fs = get_fs()
feats = fs.get_feature_group("weather_features", version=2).read()
targets = fs.get_feature_group("weather_targets", version=2).read()

df = feats.merge(targets, on="ts").sort_values("ts")
print("features:", len(feats), "| targets:", len(targets), "| joined:", len(df))
print("range:", df["ts"].min(), "->", df["ts"].max())
print("duplicate ts:", df["ts"].duplicated().sum())

expected = int((df["ts"].max() - df["ts"].min()) / pd.Timedelta("1h")) + 1
print("rows:", len(df), "| expected hourly rows:", expected)

train_ready = df.dropna()
print("rows with no NaN anywhere (usable for training):", len(train_ready))