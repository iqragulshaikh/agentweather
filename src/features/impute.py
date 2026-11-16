"""Fill gaps with a documented strategy. Never invent long gaps."""
import numpy as np
import pandas as pd

CONTINUOUS = ["temp_c", "humidity", "wind_speed_ms", "pressure_hpa",
              "cloud_pct", "uv_index", "aqi", "pm2_5", "pm10", "o3", "no2"]
MAX_GAP = 3  # hours


def long_gap_mask(s, max_gap):
    """True for NaNs that belong to a gap longer than max_gap hours."""
    is_na = s.isna()
    run_id = (is_na != is_na.shift()).cumsum()
    run_len = is_na.groupby(run_id).transform("sum")
    return is_na & (run_len > max_gap)


def impute(df):
    """Input: fused DataFrame with a 'timestamp' column. Returns (clean_df, report)."""
    df = df.copy().set_index("timestamp").sort_index()

    # 1. make missing hours explicit
    full = pd.date_range(df.index.min(), df.index.max(), freq="h", tz="UTC")
    df = df.reindex(full)
    df.index.name = "timestamp"

    # 2. wind direction -> sin/cos (angles can't be interpolated directly)
    rad = np.deg2rad(df["wind_dir_deg"])
    df["wind_sin"], df["wind_cos"] = np.sin(rad), np.cos(rad)

    cols = CONTINUOUS + ["wind_sin", "wind_cos", "wind_dir_deg", "precip_mm"]
    before = df[cols].isna()

    # 3. continuous columns: fill everything, then blank out gaps longer than MAX_GAP
    for c in CONTINUOUS + ["wind_sin", "wind_cos"]:
        too_long = long_gap_mask(df[c], MAX_GAP)
        df[c] = (df[c].interpolate(method="linear", limit_area="inside")
                      .ffill()
                      .mask(too_long))

    # 4. wind direction back from sin/cos, only where it was missing
    recon = np.degrees(np.arctan2(df["wind_sin"], df["wind_cos"])) % 360
    df["wind_dir_deg"] = df["wind_dir_deg"].fillna(recon)

    # 5. precipitation: assume dry for short gaps, leave long gaps empty
    too_long = long_gap_mask(df["precip_mm"], MAX_GAP)
    df["precip_mm"] = df["precip_mm"].fillna(0.0).mask(too_long)

    # 6. flag and report
    after = df[cols].isna()
    df["was_imputed"] = (before & ~after).any(axis=1)

    report = {
        "rows": len(df),
        "rows_imputed": int(df["was_imputed"].sum()),
        "still_missing": {c: int(n) for c, n in after.sum().items() if n > 0},
    }
    return df.reset_index(), report


if __name__ == "__main__":
    from src.ingestion.fuse import fuse
    df = fuse(past_days=3)
    df = df.drop(df.index[[10, 11]])       # 2-hour gap -> should be filled
    df = df.drop(df.index[30:38])          # 8-hour gap -> should stay NaN
    clean, report = impute(df)
    print(report)