from src.ingestion.sources import fetch_openmeteo_air, fetch_openmeteo_weather

w = fetch_openmeteo_weather(92)
a = fetch_openmeteo_air(92)
print(w.isna().sum())
print("first valid temp:", w.dropna(subset=["temp_c"])["timestamp"].min())
print("first valid uv:  ", w.dropna(subset=["uv_index"])["timestamp"].min())
print("first valid aqi: ", a.dropna(subset=["aqi"])["timestamp"].min())