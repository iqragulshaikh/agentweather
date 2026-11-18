"""24h-ahead targets. Row t gets the value observed at t+24h."""
import pandas as pd

HORIZON = 24
RAIN_THRESHOLD_MM = 0.1


def build_targets(clean):
    df = clean.copy().set_index("timestamp").sort_index()

    # shift(-24) means "24 rows ahead", which only equals 24 hours
    # if the index is a complete hourly range (impute() guarantees this)
    steps = df.index.to_series().diff().dropna().unique()
    assert len(steps) == 1 and steps[0] == pd.Timedelta("1h"), "index is not regular hourly"

    future = df.shift(-HORIZON)
    t = pd.DataFrame(index=df.index)
    t["target_temp_c"] = future["temp_c"]
    t["target_humidity"] = future["humidity"]
    t["target_precip_mm"] = future["precip_mm"]
    t["target_rain"] = (future["precip_mm"] >= RAIN_THRESHOLD_MM).astype(float) \
        .where(future["precip_mm"].notna())
    t["target_uv_index"] = future["uv_index"]
    t["target_aqi"] = future["aqi"]
    t["target_wind_speed_ms"] = future["wind_speed_ms"]
    t["target_wind_sin"] = future["wind_sin"]
    t["target_wind_cos"] = future["wind_cos"]

    t = t.dropna(how="any")          
    return t.reset_index()