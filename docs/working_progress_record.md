#Progress summary: 

##Day 1: Setup
GitHub repo and folder structure, .gitignore, venv, .env, decisions.md
Accounts for OpenWeather, AQICN, Hopsworks, Groq
City: Karachi

##Day 2: API exploration
Tested 5 endpoints and wrote a get_json() with timeout, retries and backoff
Found the AQICN problem: it returned Ahmedabad, 590 km away. A name search and a bounding-box search found no live Karachi station, so AQICN was dropped
Decision: Open-Meteo Air Quality as the primary AQI source, OpenWeather Air Pollution as the cross-check
Failure test passed (wrong key, retries, no crash)

##Day 3: Fusion
sources.py (fetchers) and fuse.py (merge into one row per UTC hour)
Open-Meteo is primary, OpenWeather goes into separate ow_ columns
Future hours removed, wind in m/s, no gaps
Output verified today
-------------------------------------------------------------------------
day1: 
structure developed

day 2:
-src/ingestion/explore_apis.py
-inspect data/raw/
-src/ingestion/inspect_raw.py
-src/ingestion/find_station.py
-src/ingestion/find_station_bounds.py
-src/ingestion/inspect_air.py

day 3 files: 
-src/ingestion/sources.py
-src/ingestion/fuse.py

day 4 files:
-src/features/impute.py
-src/features/build_features.py

day 5 files:
-installed hopswork
-src/features/hops.py
-src/features/store.py
-src/features/run_pipeline.py
-src/features/check_store.py*

day 6 files:
-src/features/target.py
-src/features/run_pipeline.py
-src/features/dry_run.py
-src/features/check_backfill.py
-src/features/diagnose.py ( for fixing issue )
-src/features/probe_history.py ( for fixing issue )
day 6b file
src/features/history.py
src/features/dry_run_history.py
