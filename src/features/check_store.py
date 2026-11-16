from src.features.hops import get_fs

fs = get_fs()
for name in ["weather_raw", "weather_features", "openweather_live"]:
    df = fs.get_feature_group(name, version=2).read()
    print(f"{name}: {len(df)} rows | {df['ts'].min()} -> {df['ts'].max()} "
          f"| duplicate ts: {df['ts'].duplicated().sum()}")