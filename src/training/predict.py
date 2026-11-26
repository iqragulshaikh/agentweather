"""One place that turns feature rows into 24 h-ahead forecasts."""
import numpy as np
import pandas as pd

CHANGE_METRICS = ["aqi", "temp_c", "humidity", "uv_index", "wind_speed_ms"]


def _clip(p, lo, hi):
    if lo is not None:
        p = np.maximum(p, lo)
    if hi is not None:
        p = np.minimum(p, hi)
    return p


def predict_metric(b, df):
    """b = a saved bundle, df = rows with the feature columns. Returns an array."""
    X = df[b["features"]].astype("float64")
    kind = b["kind"]

    if kind == "change":
        now = df[b["now_col"]].to_numpy(dtype=float)
        p = now + b["lam"] * b["model"].predict(X) if b["use_model"] else now.copy()
        p = _clip(p, *b["clip"])
        if b["metric"] == "uv_index":
            p = np.where(now == 0, 0.0, p)            # no UV at this hour today -> none tomorrow
        return p

    if kind == "wind_dir":
        ns, nc = df["wind_sin"].to_numpy(float), df["wind_cos"].to_numpy(float)
        if b["use_model"]:
            d = b["model"].predict(X)
            ns, nc = ns + b["lam"] * d[:, 0], nc + b["lam"] * d[:, 1]
        return np.degrees(np.arctan2(ns, nc)) % 360

    if kind == "rain_prob":
        return b["model"].predict_proba(X)[:, 1]

    raise ValueError(f"unknown bundle kind: {kind}")


def forecast_frame(bundles, df):
    """Forecast for ts + 24 h from every row of df (features at the origin time)."""
    out = pd.DataFrame({"ts_origin": df["ts"].to_numpy()})
    out["ts_target"] = out["ts_origin"] + pd.Timedelta(hours=24)
    for m in CHANGE_METRICS:
        out[m] = predict_metric(bundles[m], df)
    out["wind_dir_deg"] = predict_metric(bundles["wind_dir_deg"], df)
    out["rain_prob"] = predict_metric(bundles["rain_prob"], df)
    out["precip_mm"] = out["rain_prob"] * bundles["precip_mm"]["intensity"]
    return out