import json

ow = json.load(open("data/raw/openweather_air.json"))["list"][0]
print("OpenWeather AQI (1-5 scale):", ow["main"]["aqi"])
print("OpenWeather components (ug/m3):", ow["components"])

om = json.load(open("data/raw/openmeteo_air.json"))["hourly"]
# last hour that has real values
idx = max(i for i, v in enumerate(om["us_aqi"]) if v is not None)
print("Open-Meteo hour:", om["time"][idx])
print("Open-Meteo us_aqi:", om["us_aqi"][idx])
print("Open-Meteo pm2_5:", om["pm2_5"][idx], "pm10:", om["pm10"][idx])