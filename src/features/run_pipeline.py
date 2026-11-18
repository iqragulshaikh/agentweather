import sys

from src.features.build_features import build_features
from src.features.hops import get_fs
from src.features.impute import impute
from src.features.store import write_group
from src.features.targets import build_targets
from src.ingestion.fuse import fuse


def main(past_days=14):
    raw = fuse(past_days)

    ow_cols = [c for c in raw.columns if c.startswith("ow_")]
    om = raw.drop(columns=ow_cols)

    clean, report = impute(om)
    feats = build_features(clean)
    targets = build_targets(clean)
    print("impute report:", report)
    print("raw:", om.shape, "| features:", feats.shape, "| targets:", targets.shape)

    fs = get_fs()
    write_group(fs, "weather_raw", om, "Open-Meteo hourly observations, UTC")
    write_group(fs, "weather_features", feats, "Imputed + engineered features, UTC")
    write_group(fs, "weather_targets", targets, "24h-ahead targets (value at t+24h), UTC")

    if ow_cols:
        ow = raw[["timestamp"] + ow_cols].dropna(subset=ow_cols, how="all")
        if len(ow):
            write_group(fs, "openweather_live", ow, "OpenWeather live reading per run")
    print("done")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    main(days)