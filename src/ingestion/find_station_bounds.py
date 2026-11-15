import os
import requests
from dotenv import load_dotenv

load_dotenv()

r = requests.get(
    "https://api.waqi.info/map/bounds/",
    params={"token": os.getenv("AQICN_TOKEN"), "latlng": "24.6,66.8,25.2,67.4"},
    timeout=10,
)
data = r.json().get("data", [])
print("Stations found:", len(data))
for s in data:
    print(s["uid"], "|", s["station"]["name"], "|", s["station"]["time"], "| aqi:", s["aqi"])