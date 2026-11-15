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