"""Time, lag, rolling and rate-of-change features. Uses ONLY past/current data."""
import numpy as np
import pandas as pd

from src.features.impute import impute
from src.ingestion.fuse import fuse

BASE = ["temp_c", "humidity", "precip_mm", "wind_speed_ms",
        "uv_index", "aqi", "pm2_5", "pm10"]
LAGS = [1, 3, 6, 24]
WINDOWS = [6, 24]


def build_features(df):
    df = df.copy().set_index("timestamp").sort_index()
    keep = BASE + ["wind_dir_deg", "wind_sin", "wind_cos", "pressure_hpa",
                   "cloud_pct", "o3", "no2", "was_imputed"]
    out = df[keep].copy()
    new = {}

    # time features (UTC), cyclical encoding
    idx = df.index
    new["hour"] = idx.hour
    new["day_of_week"] = idx.day_of_week
    new["month"] = idx.month
    new["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
    new["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
    new["month_sin"] = np.sin(2 * np.pi * idx.month / 12)
    new["month_cos"] = np.cos(2 * np.pi * idx.month / 12)

    for c in BASE:
        s = df[c]
        for lag in LAGS:                      # value `lag` hours ago
            new[f"{c}_lag{lag}"] = s.shift(lag)
        for w in WINDOWS:                     # rolling stats over the past w hours
            new[f"{c}_mean{w}"] = s.rolling(w, min_periods=w).mean()
            new[f"{c}_std{w}"] = s.rolling(w, min_periods=w).std()
        new[f"{c}_diff1"] = s.diff(1)         # rate of change
        new[f"{c}_diff3"] = s.diff(3)

    out = pd.concat([out, pd.DataFrame(new, index=idx)], axis=1)
    return out.reset_index()


if __name__ == "__main__":
    raw = fuse(past_days=14)
    clean, report = impute(raw)
    print("impute report:", report)

    feats = build_features(clean)
    print("feature table:", feats.shape)

    # leakage sanity check: lag24 at row t must equal the value at row t-24
    i = 100
    assert feats.loc[i, "temp_c_lag24"] == feats.loc[i - 24, "temp_c"], "LEAKAGE!"
    print("lag check passed")

    complete = feats.dropna()
    print("rows without any NaN:", len(complete), "of", len(feats))
    print("\nFirst 5 columns of last row:\n", feats.tail(1).T.head(15))