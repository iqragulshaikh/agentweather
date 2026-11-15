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