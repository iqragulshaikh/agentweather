import pandas as pd
import requests

from src.ingestion.sources import LAT, LON

WEATHER = ("temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,"
           "wind_direction_10m,uv_index,pressure_msl,cloud_cover")
AIR = "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide"


def probe(name, url, hourly, start, end, extra=None):
    params = {"latitude": LAT, "longitude": LON, "timezone": "UTC",
              "hourly": hourly, "start_date": start, "end_date": end}
    params.update(extra or {})
    r = requests.get(url, params=params, timeout=60)
    print(f"\n=== {name} {start} -> {end}: HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:300])
        return
    df = pd.DataFrame(r.json()["hourly"])
    print("rows:", len(df))
    for c in df.columns[1:]:
        valid = df.dropna(subset=[c])
        first = valid["time"].min() if len(valid) else "NONE"
        print(f"  {c:22s} nulls={df[c].isna().sum():4d}  first valid={first}")
    if "precipitation" in df:
        print("  hours with precip >= 0.1 mm:", int((df["precipitation"] >= 0.1).sum()))


HF = "https://historical-forecast-api.open-meteo.com/v1/forecast"
AQ = "https://air-quality-api.open-meteo.com/v1/air-quality"

for start, end in [("2025-11-01", "2025-11-30"), ("2026-07-01", "2026-07-31")]:
    probe("historical-forecast", HF, WEATHER, start, end, {"wind_speed_unit": "ms"})
    probe("air-quality", AQ, AIR, start, end)