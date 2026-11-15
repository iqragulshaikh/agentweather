import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

LAT = float(os.getenv("LAT", 24.8607))
LON = float(os.getenv("LON", 67.0011))
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)
# "aqicn": fetch_aqicn,   # dropped: no live Karachi station (see decisions.md)

def get_json(url, params=None, retries=3, timeout=10):
    """GET with timeout and retry. Returns dict or None if all attempts fail."""
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"[attempt {attempt}/{retries}] failed: {e}")
            time.sleep(2 ** attempt)  # wait 2s, 4s, 8s
    return None


def fetch_openweather():
    return get_json(
        "https://api.openweathermap.org/data/2.5/weather",
        {"lat": LAT, "lon": LON, "appid": os.getenv("OPENWEATHER_API_KEY"), "units": "metric"},
    )


def fetch_aqicn():
    token = os.getenv("AQICN_TOKEN")
    return get_json(f"https://api.waqi.info/feed/geo:{LAT};{LON}/", {"token": token})


def fetch_openmeteo_weather():
    return get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": LAT, "longitude": LON, "timezone": "UTC",
            "hourly": "temperature_2m,relative_humidity_2m,precipitation,"
                      "wind_speed_10m,wind_direction_10m,uv_index",
            "past_days": 2, "forecast_days": 1,
        },
    )


def fetch_openmeteo_air():
    return get_json(
        "https://air-quality-api.open-meteo.com/v1/air-quality",
        {
            "latitude": LAT, "longitude": LON, "timezone": "UTC",
            "hourly": "us_aqi,pm2_5,pm10,ozone,nitrogen_dioxide",
            "past_days": 2, "forecast_days": 1,
        },
    )


def fetch_openweather_air():
    return get_json(
        "http://api.openweathermap.org/data/2.5/air_pollution",
        {"lat": LAT, "lon": LON, "appid": os.getenv("OPENWEATHER_API_KEY")},
    )


if __name__ == "__main__":
    sources = {
        "openweather": fetch_openweather,
        "aqicn": fetch_aqicn,
        "openmeteo_weather": fetch_openmeteo_weather,
        "openmeteo_air": fetch_openmeteo_air,
        "openweather_air": fetch_openweather_air, 
    }
    for name, fn in sources.items():
        data = fn()
        if data is None:
            print(f"{name}: FAILED")
            continue
        (RAW_DIR / f"{name}.json").write_text(json.dumps(data, indent=2))
        print(f"{name}: OK -> data/raw/{name}.json")