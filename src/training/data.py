from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

DATA = Path("data/dataset.parquet")
DROP = ["hour", "day_of_week", "month", "month_sin", "month_cos", "wind_dir_deg"]

# metric -> (target column, column holding the value "now")
REG = {
    "aqi": ("target_aqi", "aqi"),
    "temp_c": ("target_temp_c", "temp_c"),
    "humidity": ("target_humidity", "humidity"),
    "uv_index": ("target_uv_index", "uv_index"),
    "wind_speed_ms": ("target_wind_speed_ms", "wind_speed_ms"),
    "wind_sin": ("target_wind_sin", "wind_sin"),
    "wind_cos": ("target_wind_cos", "wind_cos"),
    "precip_mm": ("target_precip_mm", "precip_mm"),
}
CLIP = {"uv_index": (0, None), "wind_speed_ms": (0, None), "humidity": (0, 100),
        "wind_sin": (-1, 1), "wind_cos": (-1, 1), "precip_mm": (0, None)}


def load():
    df = pd.read_parquet(DATA)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    labeled = df.dropna(subset=["target_temp_c"]).reset_index(drop=True)
    num = labeled.select_dtypes(include=["number", "bool"]).columns
    feats = [c for c in num if not c.startswith("target_") and c not in DROP]
    return labeled, labeled[feats].astype("float64"), feats


def folds(n, n_splits=5, test_size=1200, gap=24):
    return list(TimeSeriesSplit(n_splits=n_splits, test_size=test_size, gap=gap)
                .split(np.arange(n)))


def clip(name, p):
    if name in CLIP:
        lo, hi = CLIP[name]
        return np.clip(p, lo, hi)
    return p