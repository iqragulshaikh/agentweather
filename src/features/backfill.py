from datetime import date, timedelta

from src.features.build_features import build_features
from src.features.hops import get_fs
from src.features.impute import impute
from src.features.store import write_group
from src.features.targets import build_targets
from src.ingestion.history import fetch_history

WARMUP = 24


def main(days=365):
    end = date.today() - timedelta(days=2)
    start = end - timedelta(days=days)
    raw = fetch_history(start, end)

    clean, report = impute(raw)
    feats = build_features(clean).iloc[WARMUP:]       # drop warm-up rows
    targets = build_targets(clean)
    targets = targets[targets["timestamp"] >= feats["timestamp"].min()]
    print("impute report:", report)
    print("raw:", raw.shape, "| features:", feats.shape, "| targets:", targets.shape)

    fs = get_fs()
    write_group(fs, "weather_raw", raw, "Open-Meteo hourly observations, UTC")
    write_group(fs, "weather_features", feats, "Imputed + engineered features, UTC")
    write_group(fs, "weather_targets", targets, "24h-ahead targets (value at t+24h), UTC")
    print("done")


if __name__ == "__main__":
    main()
    