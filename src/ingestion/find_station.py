import os
import requests
from dotenv import load_dotenv

load_dotenv()
r = requests.get(
    "https://api.waqi.info/search/",
    params={"token": os.getenv("AQICN_TOKEN"), "keyword": "karachi"},
    timeout=10,
)
for s in r.json().get("data", []):
    print(s["uid"], "|", s["station"]["name"], "|", s["time"]["stime"], "| aqi:", s["aqi"])
    