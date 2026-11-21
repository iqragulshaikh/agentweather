"""Backfill: Open-Meteo Historical Forecast + Air Quality, fetched in chunks."""
from datetime import timedelta

import pandas as pd

from src.ingestion.sources import LAT, LON, get_json

HF_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_VARS = ("temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,"
                "wind_direction_10m,uv_index,pressure_msl,cloud_cover")
AIR_VARS = "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide"
CHUNK_DAYS = 30


def _chunks(start, end, n=CHUNK_DAYS):
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=n - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def _fetch(url, hourly, start, end, extra=None):
    frames = []
    for s, e in _chunks(start, end):
        params = {"latitude": LAT, "longitude": LON, "timezone": "UTC",
                  "hourly": hourly, "start_date": s.isoformat(), "end_date": e.isoformat()}
        params.update(extra or {})
        data = get_json(url, params, timeout=60)
        if data is None:
            print(f"  chunk {s} -> {e} FAILED (left as a gap)")
            continue
        frames.append(pd.DataFrame(data["hourly"]))
        print(f"  chunk {s} -> {e} ok")
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df.pop("time"), utc=True)
    return df.drop_duplicates("timestamp")


def fetch_history(start, end):
    """start/end are datetime.date. Returns one row per UTC hour, same columns as fuse()."""
    print("weather:")
    w = _fetch(HF_URL, WEATHER_VARS, start, end, {"wind_speed_unit": "ms"})
    print("air quality:")
    a = _fetch(AQ_URL, AIR_VARS, start, end)
    if w is None or a is None:
        raise RuntimeError("history fetch failed completely")

    w = w.rename(columns={
        "temperature_2m": "temp_c", "relative_humidity_2m": "humidity",
        "precipitation": "precip_mm", "wind_speed_10m": "wind_speed_ms",
        "wind_direction_10m": "wind_dir_deg", "pressure_msl": "pressure_hpa",
        "cloud_cover": "cloud_pct"})
    a = a.rename(columns={"us_aqi": "aqi", "ozone": "o3", "nitrogen_dioxide": "no2"})

    df = w.merge(a, on="timestamp", how="outer").sort_values("timestamp")
    return df.reset_index(drop=True)