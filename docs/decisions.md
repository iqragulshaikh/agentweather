# Decisions & Issues Log

## Day 1 (Nov 13)
- Chose city: Karachi
- Why:  I live here so I can check forecasts against real
  conditions. Karachi has strong AQI variation and a coastal climate
  (sea breeze, high humidity) which makes the forecasting problem
  more interesting than a stable climate. It also has AQICN stations. 
- Done: repo, env, accounts
- Problems: OpenWeather key not active yet, takes up to a couple of hours

## Day 2 (Nov 14): API exploration

**Goal:** Test every data source for Karachi and decide which ones to use.

**Done**
- Explored 5 endpoints: OpenWeather (current), OpenWeather Air Pollution,
  Open-Meteo weather, Open-Meteo air quality, AQICN.
- Wrote `get_json()` with a timeout and 3 retries (2s, 4s, 8s backoff) so one
  failing API doesn't crash the pipeline.

**Findings**
- OpenWeather current weather has no UV or AQI; rain appears only when raining.
- Open-Meteo provides UV, precipitation, AQI and historical data, with no API key.
- With past_days=2 and forecast_days=1, Open-Meteo returns 72 hourly values.
  Future hours are model forecasts, not observations, so the pipeline must
  keep only past hours.
- Units: Open-Meteo wind is km/h, OpenWeather is m/s. Standardised on m/s (km/h / 3.6).
- Timestamps: all sources convert to UTC. Store UTC, display Asia/Karachi (UTC+5).

**ISSUE: AQICN returned the wrong city**
- The geo lookup returned "SAC ISRO Bopal, Ahmedabad, India", about 590 km away.
- Investigation: a keyword search for "karachi" found only Karachi US Consulate
  (last update 2025-03-04, no AQI). A bounding-box search over Karachi
  (24.6,66.8 to 25.2,67.4) found 0 stations.
- DECISION: drop AQICN. Use Open-Meteo Air Quality as the primary AQI source
  and OpenWeather Air Pollution as a cross-check.
- LIMITATION: Open-Meteo AQI is model-based, not a ground sensor, so it may
  smooth out local spikes.
- Note: AQICN iaqi values are AQI sub-indices, not µg/m³, so they must never
  be mixed with pollutant concentrations.

**Final data sources**
| Metric | Primary | Cross-check |
|---|---|---|
| AQI and pollutants | Open-Meteo Air Quality | OpenWeather Air Pollution |
| Temperature, humidity, wind | Open-Meteo | OpenWeather (live) |
| Precipitation, UV | Open-Meteo | none |

**Air-quality cross-check (first look)**
- OpenWeather: AQI 3/5 (1-5 scale), PM2.5 = 17.9 µg/m³, PM10 = 67.1 µg/m³.
- Open-Meteo: US AQI 89, PM2.5 = 30.3 µg/m³, PM10 = 36.2 µg/m³.
- The two sources differ, as expected for different models. This comparison is
  not yet valid: the Open-Meteo value was taken from 23:00 UTC, a future hour,
  while OpenWeather is the current hour. To be redone on the same hour in Day 3.

**Failure test:** (fill in: wrong key -> 3 retries -> FAILED, no crash, other sources OK)

## Day 3 (Nov 15): Source fusion
- Decision: Open-Meteo = primary source for all features and history.
  OpenWeather live = separate ow_ columns (cross-check and fallback), since it
  has no history.
- Pipeline keeps only past hours (timestamp <= current UTC hour).
- Wind requested in m/s directly via wind_speed_unit=ms.
- Added pressure and cloud cover as extra features (useful for rain).
- Result: 59 rows = 59 expected hourly rows, 0 missing in primary columns.
- Same-hour air check: PM2.5 27.5 (Open-Meteo) vs 17.6 (OpenWeather);
  PM10 52.5 vs 65.2. Same order of magnitude, not identical (different models).

## Day 4 (Nov 16): Imputation and features
- Imputation: reindex to a full hourly range; linear interpolation for gaps
  <= 3h; forward-fill at the end of the data (<= 3h); wind direction via
  sin/cos; precipitation filled with 0 for short gaps; gaps longer than 3h
  left as NaN and reported; was_imputed flag per row.
- Features: hour/day/month, sin/cos encodings, lags (1,3,6,24h), rolling
  mean/std (6h, 24h), diff1/diff3 for 8 base metrics. Total 104 columns.
- Result: 350 rows (14 days), 326 complete. First 24h lost to lags.
- Leakage check: lag24(t) == value(t-24), passed.
- ISSUE: gap test (2h gap + 8h gap) left only 2 of 8 hours empty in the long
  gap, because interpolate(limit=3) and ffill(limit=3) stacked.
  FIX: fill everything first, then blank out any NaN run longer than 3h
  (long_gap_mask). Precipitation follows the same rule.
  RE-TEST: rows_imputed = 2, 8 hours still missing per column. Passed.
- ISSUE: impute() returned None after an edit removed its last lines.
  LESSON: after editing a function, check that the return is still there.
- Problems: ran impute.py as a shell command; files saved in src/ingestion/
  instead of src/features/. Fixed by moving them and using `python -m`.

## Day 5 (Nov 17): Hopsworks feature store
- Feature groups (version 2): weather_raw (Open-Meteo), openweather_live
  (ow_ columns), weather_features (imputed + 104 engineered columns).
  Primary key and event time: ts (UTC).
- Decision: OpenWeather live data has its own group, because it only exists for
  the current hour and would be overwritten with NaN by re-writes of older hours.
- Idempotency: Hopsworks upserts on the primary key. Test: (fill in your numbers)
- ISSUE 1: pip install typo (hopswork instead of hopsworks). Fixed spelling.
- ISSUE 2: login failed with 403 "no valid role" because the project name in
  .env did not match. Fixed with the exact project name.
- ISSUE 3: "delta library is not installed". FIX: pip install deltalake.
- ISSUE 4: direct write failed with an HDFS "RPC listener disconnected" error
  on Windows. FIX: stream=True (writes go through Kafka and a Hopsworks
  materialization job) and a new feature group version (2).
- All numeric columns cast to float64; ts cast to microseconds to avoid a
  precision warning.

## Day 6 (Nov 18-19): Backfill, targets and data layer

**Goal:** build a clean year of hourly history with 24h-ahead targets in the
Feature Store.

### 1. Targets
- Target for row t = value observed at t+24h (temp, humidity, UV, AQI, wind
  speed, precip_mm). Rain is a binary target (precip >= 0.1 mm). Wind
  direction is stored as sin/cos.
- Stored in a separate feature group (`weather_targets`) so targets cannot leak
  into the features.
- The newest 24 rows have no target and are used for forecasting only.
- Check: target(t) == observed value at t+24h, passed.

### 2. First backfill attempt (past_days=92) and the problem
- Result: 2,215 hourly rows, but weather columns were empty for the first 552 h
  and UV for the first 962 h. Only about 52 days were usable (autumn only).
- Diagnosis: the forecast endpoint returns weather only from Sep 10 and UV from
  Sep 27, whatever past_days says. AQI covered the full window.
  The limit is in the source, not the pipeline. impute() correctly refused to
  invent 23-40 days of data.
- Finding: rain at t+24 occurred in only 1.44% of hours (about 18 events), too
  few for a rain classifier.

### 3. Fix: date-range history endpoints
- Docs check: the Archive API has no uv_index. The Historical Forecast API has
  the same variables as the live API (including UV), covers about 2022 onwards
  and accepts start_date/end_date. The Air Quality API accepts date ranges too.
- DECISION: backfill 12 months from the Historical Forecast API (weather) and
  the Air Quality API, in 30-day chunks, with the same column names as the live
  pipeline (no train/serve skew).
- Probe: Nov 2025 and Jul 2026 returned HTTP 200 with 0 nulls in all columns.
- Dry run (before writing anything): 8,784 hourly rows (Nov 19 2025 -> Nov 19
  2026), 0 gaps, 0 imputed, 26/26 chunks fetched, target check passed.
- Rain by month: about 0-3% Nov-May, 11.5% Jun, 18% Jul, 24% Aug, 10% Sep,
  1-2% Oct-Nov. 553 rain hours of 8,760 (6.3%).
- Values physically plausible: temp 9.3-41.2 C, humidity 7-100%, wind up to
  6.95 m/s.

### 4. Issues and fixes
- ISSUE: Hopsworks upserts replace whole rows, so rewriting a window would
  overwrite its first 24 rows (incomplete lags) with NaN features.
  FIX: drop 24 warm-up rows before every write (`feats.iloc[24:]`).
- ISSUE: the 14-day run was made before this fix was in run_pipeline.py. It
  overwrote about 24 good rows (~Nov 7) with NaN lags. Found by comparing the
  printed shapes (features 353 = raw 353, expected 329).
  FIX: added the trim, then re-ran with a 21-day window so the damaged rows were
  recomputed from complete history.
- ISSUE: Kafka errors during upload (`_TIMED_OUT`, then `_TRANSPORT`), before
  any data was written. They were temporary network problems.
  FIX: retried; write_group now retries 3 times (30s/60s backoff). Retrying is
  safe because writes are upserts.
- LESSON: compare printed row counts before every write, and check that a fix
  is really in the file.

### 5. Final verification (check_backfill)
- features 8,801 | targets 8,777 | joined 8,777 | duplicate ts 0
- rows = expected hourly rows (8,777), so no gaps
- rows with no NaN anywhere: 8,777 of 8,777
- Range: Nov 20 2025 -> Nov 20 2026. The newest 24 feature rows have no target
  (forecasting only).

### 6. Limitations (for the report)
- Precipitation, AQI and UV are model output, not sensor or gauge data.
  AQI (max 165) probably smooths real Karachi pollution spikes. UV max 7.85
  looks low for summer (to check in EDA).
- Only one year of history: each season is seen once.
- The stitched forecast series can change when the model version changes.
- Rain validation: Oct-Nov has only 1-2% rain, so a last-weeks validation split
  can't evaluate the rain classifier. Use expanding-window CV with monsoon folds.

## Day 7 (20 NOV): EDA and naive baseline
- Data: 8,801 hourly rows (8,777 with targets), Nov 2025 -> Nov 2026. Charts in
  Karachi time. 0 missing values. Charts saved in docs/eda/.
- AQI: right-skewed (median 83, 90th pct 120, 99th pct 153, max 165). 21.9% of
  hours > 100, 1.7% > 150. Worst in winter (monthly mean about 105-118), cleanest
  in the monsoon (about 75-80). Almost no daily cycle (hourly mean 87-92).
  Correlates with pressure (+0.48) and wind speed (-0.41).
- Temperature: 9.3-41.2 C, mean 26.5. Coldest Jan (about 19), hottest May-Jun
  (about 30.5). Daily minimum at 06:00 and maximum at 14:00 Karachi time.
- Humidity: 7-100%, mean 66. Lag-24 autocorrelation 0.84.
- UV: zero at night (about 4,600 hours), peak at 13:00. Highest in Apr-Aug with
  daily maxima capped at 7.8-7.85, probably too low for the latitude (to verify).
- Wind: mean 3.0 m/s (max 6.95). Direction rotates from WNW (night/morning) to SW
  (afternoon), consistent with the sea breeze.
- Precipitation: 553 rain hours (>= 0.1 mm), 464 of them in Jun-Sep; total about
  111 mm (model-based). Mostly light: July is 19.1 mm over 149 hours.
- Autocorrelation at lag 24: temp 0.97, UV 0.98, humidity 0.84, AQI 0.71,
  wind speed 0.71, precipitation 0.01.
- Naive baseline (value 24 h ago), validation-like last 20% (since about Sep 8):
  | metric | RMSE | MAE | R2 |
  | AQI | 14.56 | 10.75 | 0.315 |
  | Temperature | 1.085 | 0.797 | 0.890 |
  | Humidity | 12.25 | 8.35 | 0.682 |
  | UV | 0.352 | 0.078 | 0.975 |
  | Wind speed | 0.852 | 0.644 | 0.295 |
  | Precipitation | 0.081 | 0.008 | -0.850 |
  | Wind direction (error, deg) | 36.8 | 25.5 | n/a |
  UV daytime-only MAE 0.246. Rain classifier baseline: precision = recall = F1
  = 0.24 (rain rate 2.1%); full year 0.35 (rain rate 6.3%).
- Implications for modelling:
  - Temperature and UV baselines are very strong, so expect small gains.
  - AQI, wind speed and humidity have the most room to improve.
  - Precipitation (mm) baseline is worse than a constant, so judge rain with the
    classifier (precision, recall, PR-AUC), never accuracy.
  - The last 20% contains little rain (2.1%), so use expanding-window CV with
    monsoon folds.
- Limitations: UV maximum looks low; AQI is smooth and probably underestimates
  real spikes; rain total (about 111 mm) to be checked against a climate source;
  one year of history only.
- Problems: (fill in, or "None")

## Day 8 (21 NOV): Classical ML (Ridge, Random Forest) with honest validation

**Goal:** train the first two model families and compare them with the naive
baseline (value 24 h ago) on all metrics.

### 1. Setup
- Expanding-window CV, 5 folds x 1,200 h (50 days). Folds 3-4 are the monsoon
  (Jun 23 - Oct 1). A 24 h gap between training and validation, because the
  target looks 24 h ahead (no gap = leakage).
- Models predict the change from the current value (target minus now);
  precipitation is predicted directly. Features are scaled inside a pipeline.
- Dropped month, hour, weekday and raw wind-direction features (with one year
  of data month features would memorize the year; hour and direction stay as
  sin/cos). 97 features.
- Models: Ridge (alpha 10), Random Forest (150 trees, min leaf 5,
  max_features 0.33). Rain: logistic regression and Random Forest classifier.

### 2. First results (mean RMSE over folds: naive / Ridge / RF)
- AQI 11.53 / 11.23 / 12.58; humidity 8.31 / 9.60 / 8.49;
  temperature 0.974 / 1.113 / 1.052; UV daytime 0.715 / 0.659 / 0.677;
  wind speed 0.901 / 0.904 / 0.900; wind direction 28.7 / 27.1 / 26.9 deg.
- Precipitation (mm): negative R2 for every model, so direct regression is
  unusable.
- Rain (PR-AUC / Brier): logistic regression 0.252 / 0.068, Random Forest
  0.191 / 0.073, naive 0.138 / 0.114, constant 0.089 / 0.085. Fold 5 has only
  about 18 rain events (noisy).

### 3. ISSUE: models lost to the baseline on several metrics
- Models won mostly in folds 4-5 (Aug-Nov) and lost in folds 1-3 (Mar-Aug).
- Diagnosis (bias per fold): AQI (RF) +13.4 / +8.0 in folds 1-2, humidity (RF)
  -7.7 / -4.3, wind speed -0.7 in fold 2. The winter-only training window teaches
  a seasonal drift that does not apply in spring and summer. Temperature bias was
  at most 0.5, so its loss was variance (noise), not drift.
- FIX 1: much stronger Ridge regularization (alpha 10 -> 10,000) improved every
  metric (AQI 11.23 -> 10.00, humidity 9.76 -> 8.08, temperature 1.113 -> 0.970,
  wind 0.904 -> 0.833).
- FIX 2: shrink the predicted correction: prediction = now + lambda x predicted
  change (lambda 0 = baseline, 1 = full model). Lambda 0.25-0.75 was best.

### 4. ISSUE: tuning on the reported folds is optimistic
- FIX: leave-one-fold-out selection. The setting (model, alpha, lambda) is chosen
  using 4 folds and scored on the 5th.
- Honest result (naive -> selected RMSE, folds better): AQI 11.53 -> 9.71
  (-15.8%, 5/5), wind speed 0.901 -> 0.827 (-8.2%, 5/5), humidity 8.31 -> 8.06
  (-3.1%, 5/5), temperature 0.974 -> 0.958 (-1.6%, 4/5).
- Choices were stable: AQI picked Ridge alpha 1000 lambda 0.75 in all 5 rounds;
  humidity picked Random Forest lambda 0.5 in 4 of 5; temperature picked Ridge
  alpha 10 lambda 0.25 every time. The alpha grid optimum is not at its edge.
- AQI fold 1 went from -10% (Ridge alpha 10) to +8% after the fix.

### 5. Conclusions and decisions
- Models clearly beat the baseline on AQI and wind speed, modestly on humidity.
  Temperature only ties it (0.01-0.02 C per fold); the 24 h-ago value is very
  hard to beat for temperature.
- Candidate set for the training pipeline: Ridge (several alphas), Random Forest,
  each with a shrink factor lambda; logistic regression for rain. The pipeline
  picks the best candidate per metric by walk-forward validation and registers it
  only if it beats the naive baseline.
- Precipitation (mm) will be P(rain) x typical rain intensity.
- UV and wind direction are not tuned yet.

### 6. Minor notes
- Humidity at alpha 10 differs between scripts (9.596 vs 9.758) because the first
  script clipped predictions to 0-100%.
- CV is pessimistic: production retrains daily, while CV folds retrain only every
  50 days.

### 7. Limitations (for the report)
- Candidate grids were widened after seeing first results, so some optimism remains.
- One year of data only: each season is seen once, and spring/summer folds are
  validated by a model that never saw those seasons.
- Humidity gain is modest; temperature gain is practically zero.

## Day 9 (22 NOV): Statistical family (SARIMAX)

### 1. Model and protocol
- statsmodels SARIMAX with 4 daily sin/cos harmonics as exog (a seasonal period of
  24 is slow on 8,000+ hourly rows) and AR(2) errors. Univariate. Prophet skipped
  (build-tool/install risk on Windows).
- Same protocol as Ridge/RF: fit on the training rows of each fold; for every
  validation hour, project the current deviation 24 steps ahead and add the daily
  profile; same folds, same 24 h gap, same lambda shrinkage. Forecast logic
  verified against statsmodels' forecast() at 3 origins (4 decimals).
- Metrics: AQI, temperature, humidity, wind speed (UV is zero at night and wind
  direction is circular; to be tuned later).

### 2. Results: expanding window
- Mean RMSE, naive / full model / best lambda: AQI 11.53 / 13.55 / 11.12 (0.25);
  humidity 8.31 / 11.73 / 8.17 (0.25); temperature 0.974 / 2.166 / 0.974 (0);
  wind 0.901 / 1.268 / 0.853 (0.25).
- ISSUE: the full model loses to the naive baseline. Temperature RMSE 3.34 and
  3.08 in folds 1-2 (naive 1.69 and 0.77) but 1.19 in fold 4 (naive 0.67). AR sums
  about 0.98.
- Hypothesis: the daily profile fitted on winter is stale in spring; the model
  lets that error decay, although it repeats every day at the same hour.

### 3. Fix tested (Day 9b): rolling window
- Refit every 7 days on the last 60 days, with the same 24 h cut-off.
- Mean RMSE, full / best lambda: AQI 12.83 / 10.92 (0.25); humidity 9.52 / 7.76
  (0.25); temperature 1.608 / 0.974 (0); wind 0.984 / 0.823 (0.5).
- Folds 1-4 improved (temperature fold 2: 3.08 -> 1.29), supporting the hypothesis.
  Fold 5 (Oct-Nov) got worse (temperature 1.44 -> 2.11, AQI 14.7 -> 18.5):
  60 days before October still contain the monsoon. Fewer rows also make the AR
  estimates less stable. So a recent window is not uniformly better.

### 4. Selection across all families (leave-one-fold-out, honest)
- AQI 11.53 -> 9.71 (-15.8%, 5/5 folds, Ridge alpha 1000 lambda 0.75 chosen every
  time); humidity 8.31 -> 7.94 (-4.5%, 4/5); temperature 0.974 -> 0.958 (-1.6%,
  4/5); wind 0.901 -> 0.843 (-6.5%, 5/5).
- Adding SARIMAX-rolling as a candidate made wind worse (0.827 -> 0.843):
  Ridge and SARIMAX-rolling are equivalent on average (0.821 vs 0.823), so the
  selection flips between them. More candidates = more selection noise.

### 5. Conclusions
- Three families covered so far: classical ML (Ridge, RF), statistical (SARIMAX
  expanding and rolling); the LSTM is next.
- Clear wins: AQI and wind speed. Small win: humidity (RF, Ridge, SARIMAX-rolling
  are equivalent within noise). Temperature only ties the baseline.
- For the training pipeline: keep the candidate set small and require a candidate
  to beat the baseline in at least 4 of 5 folds (to be decided at registry time).

### 6. Limitations
- One year of history; spring/summer folds are validated by models that never saw
  those seasons; the 60-day window is also unrepresentative at season transitions.
- Candidate grids were widened after seeing first results (some optimism remains).
- SARIMAX uses only the metric's own history (no pressure, wind, humidity).
## Day 10: Deep learning family (LSTM, PyTorch CPU) and model selection rule

### 1. Model
- One LSTM (1 layer, 32 units, dropout 0.2, weight decay 1e-4, gradient clipping),
  4 outputs (AQI, temperature, humidity, wind speed). Input: last 48 h of 16
  signals (pollutants, weather, wind sin/cos, pressure, cloud, hour sin/cos);
  precipitation on log1p scale; inputs scaled with training rows only.
- Target: scaled 24 h change (scale only, no mean subtraction), same lambda
  shrinkage as before. Early stopping on the latest 10% of the training rows
  (24 h gap before it), 3 seeds averaged, max 30 epochs, Adam lr 1e-3, batch 128.
  Same 5 folds and 24 h gap as every other model. Total run time: 1.0 min.

### 2. Results (mean RMSE over folds, naive / full model / best lambda)
- AQI 11.53 / 10.96 / 10.93 (0.75, -5.2%); humidity 8.31 / 8.03 / 8.02 (0.75,
  -3.6%); temperature 0.974 / 0.969 / 0.964 (0.5, -1.0%); wind 0.901 / 0.860 /
  0.859 (0.75, -4.7%).
- The LSTM beats the baseline on all four metrics, roughly ties Random Forest, and
  is behind Ridge on AQI, temperature and wind.
- Early stopping triggered after 5-10 epochs, i.e. the best epoch was 1-6: the
  network overfits quickly with about 7,000 rows.
- Early-stop loss vs the "no change" loss per fold: folds 1, 4 and 5 about 12%
  lower (skill), fold 2 equal (no skill), fold 3 4% lower. This matches the RMSE
  results. (Early-stop loss values alone cannot be read as skill, because the
  "no change" loss differs per fold.)

### 3. Selection across all families (leave-one-fold-out, honest)
- AQI 11.53 -> 9.71 (-15.8%, 5/5); humidity 8.31 -> 7.94 (-4.5%, 4/5);
  wind 0.901 -> 0.843 (-6.5%, 5/5); temperature 0.974 -> 0.972 (-0.2%, 3/5).
- ISSUE: adding the LSTM as a candidate made the temperature result worse
  (-1.6%, 4/5 before). In fold 1 the selection picked the LSTM, which was worse
  than naive there (1.727 vs 1.685). With several near-equal candidates, the
  winner on 4 folds is partly luck (selection noise).
- DECISION (rule): a candidate replaces the naive forecast for a metric only if
  it improves RMSE by at least 2% and beats naive in at least 4 of 5 folds
  (leave-one-fold-out). Result: AQI, humidity and wind use a model; temperature
  keeps the naive baseline (same hour 24 h ago): no family beats it robustly.

### 4. Conclusions
- Three families trained and compared: classical ML (Ridge, Random Forest),
  statistical (SARIMAX expanding and rolling), deep learning (LSTM).
- Clear wins: AQI (-15.8%) and wind speed (-6.5%); small win: humidity (-4.5%);
  temperature ties the baseline.
- Open items: rain, UV and wind direction (Day 11); registry and SHAP (Day 12).

### 5. Limitations
- One year of data; the LSTM overfits after 1-6 epochs.
- Candidate grids were widened after seeing early results (some optimism).
- Selection noise grows with the number of candidates.

## Day 11: UV, wind direction, rain probability, precipitation

### 1. Setup
- UV: Ridge/RF on the 24 h change, clipped at 0, scored on daytime hours only
  (hours with UV > 0 at the target time); RMSE and MAE both reported.
- Wind direction: Ridge/RF on the change of the sin/cos vector, converted back to an
  angle with atan2, scored by angular error (lambda shrink applied to the vector).
- Rain probability: logistic regression (C 0.01, 0.1, 1) and Random Forest classifier;
  baselines: climatology (training base rate) and "raining now". Metrics: PR-AUC,
  Brier score, Brier skill score (BSS) vs climatology, calibration table.
- Precipitation (mm) = P(rain) x mean intensity of rainy hours in the training rows.

### 2. Results
- UV (daytime): RMSE 0.715 -> 0.659 (Ridge alpha 10, lambda 1; -7.9%, 5/5 folds), but
  MAE 0.313 -> 0.350 (+12%): the model corrects large misses (cloudy/hazy days) and
  adds small noise on ordinary hours. Winner sits at the edge of both grids.
- Wind direction: angular RMSE 28.7 -> 25.9 deg (Ridge alpha 100, lambda 0.75; -9.7%,
  5/5 folds); MAE also improves (19.3 -> about 17.5-18.0 deg).
- Rain probability (mean over folds): logreg C=0.01 PR-AUC 0.262 / Brier 0.0708 /
  BSS 0.140; C=0.1 0.252 / 0.0683 / 0.152; C=1 0.244 / 0.0696 / 0.134; RF 0.195 /
  0.0725 / 0.109; climatology 0.089 / 0.0848; naive (raining now) 0.138 / 0.1137 /
  -0.513. BSS per fold (C=0.1): 0.003, 0.000, 0.158, 0.321, 0.279: no skill in the
  dry-season folds 1-2, clear skill in folds 3-5 (fold 5 has only ~18 rain events).
- Precipitation (mm): RMSE climatology 0.1011, zero 0.1021, naive 0.1366,
  logreg C=0.01 0.0996 (skill about +0.02), C=0.1 0.1033 (skill -0.18), RF 0.1060.
  No demonstrated skill over climatology.

### 3. ISSUE: rain probabilities are too low (calibration)
- Pooled calibration of logreg C=0.1: predicted vs observed rain rate: 0.5% vs 2.4%,
  3.3% vs 5.8%, 7.2% vs 11.0%, 14.1% vs 18.8%, 24.3% vs 30.9%, 37.8% vs 51.3%,
  56.9% vs 78.8%. Ranking is good, absolute values are about a quarter to a third
  too low.
- Likely cause (not yet tested): the expanding window trains on dry months, so the
  model's base rate is too low when the monsoon arrives.
- Alert thresholds (pooled, precision / recall): P >= 0.1: 0.29 / 0.60; 0.2: 0.43 /
  0.37; 0.3: 0.55 / 0.23; 0.5: 0.79 / 0.05. Proposed rule: "rain possible" at 0.1,
  "rain likely" at 0.3. Raw probabilities are not quoted as true percentages.

### 4. Selection (leave-one-fold-out, rule: >= 2% and >= 4 of 5 folds)
- AQI -15.8% (5/5, MODEL); humidity -4.5% (4/5, MODEL); temperature -0.2% (3/5, naive
  baseline); UV daytime -7.9% (5/5, MODEL); wind direction -9.7% (5/5, MODEL);
  wind speed -6.5% (5/5, MODEL).

### 5. Conclusions
- Five of six metrics beat the baseline under the rule, plus rain probability.
  Temperature ties the baseline; the rain amount ties climatology.
- The probability of rain can be forecast; the amount of rain cannot be forecast
  better than the average from one year of data.

  - Scorecard (frozen method vs naive, mean RMSE over folds, folds better): AQI 11.532 ->
  9.714 (15.8%, 5/5); humidity 8.314 -> 8.032 (3.4%, 5/5); wind speed 0.901 -> 0.822
  (8.8%, 5/5); UV daytime 0.715 -> 0.659 (7.9%, 5/5); wind direction 28.656 -> 25.871
  deg (9.7%, 5/5); temperature 0.974 -> 0.958 (1.6%, 4/5: fails the 2% rule, so the
  naive baseline is used); rain probability: mean BSS 0.152, PR-AUC 0.252, positive in
  5/5 folds; precipitation (mm): skill vs climatology -0.178, intensity 0.201 mm per
  rainy hour, flagged indicative only.
- Winners: Ridge (classical ML) for AQI, humidity, wind speed, UV, wind direction;
  logistic regression for rain probability; naive for temperature. SARIMAX and LSTM
  were competitive but did not clear the "simpler model unless >= 2% better" rule.
- First forecast sanity check: UV is 0 at night and peaks at 5.06 at 13:00; temperature
  19.3-30.2 C (naive); humidity opposite to temperature; wind direction rotates
  N -> SW -> NW (sea breeze); AQI flat at 103-117; rain probability 0-2%.
  Caveat: wind direction is unreliable when speed < 1 m/s (11:00: 0.94 m/s).