"""Fetch raw data from each source and return clean, UTC-indexed DataFrames."""
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

LAT = float(os.getenv("LAT", 24.8607))
LON = float(os.getenv("LON", 67.0011))


def get_json(url, params=None, retries=3, timeout=10):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"[attempt {attempt}/{retries}] {url} failed: {e}")
            time.sleep(2 ** attempt)
    return None


def fetch_openmeteo_weather(past_days=2):
    data = get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": LAT, "longitude": LON, "timezone": "UTC",
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,"
                      "wind_speed_10m,wind_direction_10m,uv_index,"
                      "pressure_msl,cloud_cover",
            "wind_speed_unit": "ms",  # m/s, same as OpenWeather
            "past_days": past_days, "forecast_days": 1,
        },
    )
    if data is None:
        return None
    df = pd.DataFrame(data["hourly"])
    df["timestamp"] = pd.to_datetime(df.pop("time"), utc=True)
    return df.rename(columns={
        "temperature_2m": "temp_c",
        "relative_humidity_2m": "humidity",
        "precipitation": "precip_mm",
        "wind_speed_10m": "wind_speed_ms",
        "wind_direction_10m": "wind_dir_deg",
        "pressure_msl": "pressure_hpa",
        "cloud_cover": "cloud_pct",
    })


def fetch_openmeteo_air(past_days=2):
    data = get_json(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        {
            "latitude": LAT, "longitude": LON, "timezone": "UTC",
            "hourly": "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
            "past_days": past_days, "forecast_days": 1,
        },
    )
    if data is None:
        return None
    df = pd.DataFrame(data["hourly"])
    df["timestamp"] = pd.to_datetime(df.pop("time"), utc=True)
    return df.rename(columns={
        "us_aqi": "aqi", "ozone": "o3", "nitrogen_dioxide": "no2",
    })


def fetch_openweather_live():
    """One-row DataFrame for the current hour, columns prefixed ow_."""
    key = os.getenv("OPENWEATHER_API_KEY")
    w = get_json("https://api.openweathermap.org/data/2.5/weather",
                 {"lat": LAT, "lon": LON, "appid": key, "units": "metric"})
    a = get_json("http://api.openweathermap.org/data/2.5/air_pollution",
                 {"lat": LAT, "lon": LON, "appid": key})
    if w is None and a is None:
        return None
    row = {"timestamp": pd.Timestamp.now(tz="UTC").floor("h")}
    if w is not None:
        row["ow_temp_c"] = w["main"]["temp"]
        row["ow_humidity"] = w["main"]["humidity"]
        row["ow_wind_speed_ms"] = w["wind"]["speed"]
        row["ow_wind_dir_deg"] = w["wind"].get("deg")
        row["ow_precip_mm"] = w.get("rain", {}).get("1h", 0.0)
    if a is not None:
        item = a["list"][0]
        row["ow_aqi_1to5"] = item["main"]["aqi"]
        row["ow_pm2_5"] = item["components"]["pm2_5"]
        row["ow_pm10"] = item["components"]["pm10"]
    return pd.DataFrame([row])