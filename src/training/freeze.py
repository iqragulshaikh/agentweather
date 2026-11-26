"""Day 12: freeze the final methods, train on all data, save bundles, first forecast."""
import datetime as dt
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from src.training.data import REG, load
from src.training.predict import forecast_frame

R = Path("docs/results")
MODELS = Path("models")
MODELS.mkdir(exist_ok=True)
MIN_GAIN_PCT, MIN_FOLDS = 2.0, 4

# metric -> (results file, metric name in that file, ridge alpha, lambda, 'now' column, clip)
CHANGE = {
    "aqi":           ("day8b_diagnose.csv", "aqi", 1000, 0.75, "aqi", (0, None)),
    "humidity":      ("day8b_diagnose.csv", "humidity", 1000, 0.5, "humidity", (0, 100)),
    "wind_speed_ms": ("day8b_diagnose.csv", "wind_speed_ms", 100, 0.5, "wind_speed_ms", (0, None)),
    "uv_index":      ("day11_uv.csv", "uv_index_day", 10, 1.0, "uv_index", (0, None)),
    "temp_c":        ("day8b_diagnose.csv", "temp_c", 10, 0.25, "temp_c", (None, None)),
}
WIND_DIR = ("day11_winddir.csv", "wind_dir_deg", 100, 0.75)


def scorecard(file, metric, alpha, lam):
    df = pd.read_csv(R / file)
    g = df[(df.metric == metric) & (df.model == f"ridge_a{alpha}") & np.isclose(df.lam, lam)]
    if g.empty:
        raise SystemExit(f"no rows for {metric} ridge_a{alpha} lam={lam} in {file}")
    g = g.sort_values("fold")
    naive, mod = g["naive"].to_numpy(), g["rmse"].to_numpy()
    gain = (1 - mod.mean() / naive.mean()) * 100
    better = int((mod < naive).sum())
    return dict(naive=round(naive.mean(), 3), model=round(mod.mean(), 3),
                gain_pct=round(gain, 1), folds_better=f"{better}/{len(g)}",
                passes=bool(gain >= MIN_GAIN_PCT and better >= MIN_FOLDS))


def ridge(alpha):
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha))


labeled, X, feats = load()
now_utc = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
meta = dict(trained_at=now_utc, n_rows=len(labeled), sklearn=sklearn.__version__,
            data_from=str(labeled["ts"].min()), data_to=str(labeled["ts"].max()))
bundles, cards = {}, {}

# ---- regression on the 24 h change (AQI, humidity, wind speed, UV, temperature)
for metric, (file, cname, alpha, lam, now_col, clip) in CHANGE.items():
    card = scorecard(file, cname, alpha, lam)
    tgt, cur = REG[metric]
    change = labeled[tgt].to_numpy() - labeled[cur].to_numpy()
    bundles[metric] = dict(kind="change", metric=metric, model=ridge(alpha).fit(X, change),
                           lam=lam, now_col=now_col, clip=clip, features=feats,
                           use_model=card["passes"], cv=card, alpha=alpha, **meta)
    cards[metric] = card

# ---- wind direction: change of the sin/cos vector
file, cname, alpha, lam = WIND_DIR
card = scorecard(file, cname, alpha, lam)
change = np.column_stack([labeled["target_wind_sin"] - labeled["wind_sin"],
                          labeled["target_wind_cos"] - labeled["wind_cos"]])
bundles["wind_dir_deg"] = dict(kind="wind_dir", metric="wind_dir_deg",
                               model=ridge(alpha).fit(X, change), lam=lam, features=feats,
                               use_model=card["passes"], cv=card, alpha=alpha, **meta)
cards["wind_dir_deg"] = card

# ---- rain probability (logistic regression) and precipitation (mm)
rain = pd.read_csv(R / "day11_rain.csv")
r = rain[rain.model == "logreg_C0.1"].sort_values("fold")
bss_ok = int((r["BSS"] > 0).sum())
rain_card = dict(mean_BSS=round(r["BSS"].mean(), 3), mean_PR_AUC=round(r["PR_AUC"].mean(), 3),
                 folds_BSS_positive=f"{bss_ok}/{len(r)}",
                 passes=bool(bss_ok >= MIN_FOLDS and r["BSS"].mean() >= 0.05))
y_rain = labeled["target_rain"].astype(int)
clf = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=3000)).fit(X, y_rain)
bundles["rain_prob"] = dict(kind="rain_prob", metric="rain_prob", model=clf, features=feats,
                            use_model=True, cv=rain_card, thresholds={"possible": 0.1, "likely": 0.3},
                            **meta)
cards["rain_prob"] = rain_card

pr = pd.read_csv(R / "day11_precip.csv")
skill = float(pr[pr.model == "logreg_C0.1"]["skill_vs_clim"].mean())
intensity = float(labeled.loc[y_rain == 1, "target_precip_mm"].mean())
bundles["precip_mm"] = dict(kind="precip", metric="precip_mm", intensity=intensity,
                            cv=dict(skill_vs_clim=round(skill, 3), indicative_only=skill <= 0), **meta)
cards["precip_mm"] = dict(skill_vs_clim=round(skill, 3), intensity_mm_per_rainy_hour=round(intensity, 3),
                          indicative_only=skill <= 0)

for name, b in bundles.items():
    joblib.dump(b, MODELS / f"{name}.joblib")

print("=== Frozen methods vs cross-validation (rule: gain >= 2% and >= 4 of 5 folds) ===")
print(pd.DataFrame(cards).T.to_string())
print("\nuse_model flags:", {k: v.get("use_model") for k, v in bundles.items() if "use_model" in v})
print(f"saved {len(bundles)} bundles to {MODELS}/  (trained on {len(labeled)} rows)")

# ---- first real forecast: the newest 24 rows have features but no target yet
df = pd.read_parquet("data/dataset.parquet")
df["ts"] = pd.to_datetime(df["ts"], utc=True)
latest = df.sort_values("ts").tail(24)
loaded = {n: joblib.load(MODELS / f"{n}.joblib") for n in bundles}
fc = forecast_frame(loaded, latest)
fc["time_karachi"] = fc["ts_target"].dt.tz_convert("Asia/Karachi").dt.strftime("%a %H:%M")
cols = ["time_karachi", "temp_c", "humidity", "aqi", "uv_index", "wind_speed_ms",
        "wind_dir_deg", "rain_prob", "precip_mm"]
print("\n=== Forecast for the 24 hours after the last row of data/dataset.parquet ===")
print(fc[cols].round(2).to_string(index=False))
fc.to_csv(R / "first_forecast.csv", index=False)