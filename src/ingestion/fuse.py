import pandas as pd

from src.ingestion.sources import (
    fetch_openmeteo_air,
    fetch_openmeteo_weather,
    fetch_openweather_live,
)


def fuse(past_days=2):
    """One row per UTC hour, past hours only."""
    primary = [f for f in (fetch_openmeteo_weather(past_days),
                           fetch_openmeteo_air(past_days)) if f is not None]
    if not primary:
        raise RuntimeError("Both primary sources failed")

    df = primary[0]
    for other in primary[1:]:
        df = df.merge(other, on="timestamp", how="outer")

    live = fetch_openweather_live()
    if live is not None:
        df = df.merge(live, on="timestamp", how="outer")

    now = pd.Timestamp.now(tz="UTC").floor("h")
    df = df[df["timestamp"] <= now]            # drop future (forecast) hours
    df = df.drop_duplicates("timestamp").sort_values("timestamp")
    return df.reset_index(drop=True)


if __name__ == "__main__":
    df = fuse()
    print("shape:", df.shape)
    print("range:", df["timestamp"].min(), "->", df["timestamp"].max())
    expected = int((df["timestamp"].max() - df["timestamp"].min()) / pd.Timedelta("1h")) + 1
    print("rows:", len(df), "| expected hourly rows:", expected)
    print("\nMissing values per column:\n", df.isna().sum())
    print("\nLast row:\n", df.tail(1).T)
    live_rows = df.dropna(subset=["ow_pm2_5"])
    print("\nAir cross-check (same hour):\n",
          live_rows[["timestamp", "pm2_5", "ow_pm2_5", "pm10", "ow_pm10"]])