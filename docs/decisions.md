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