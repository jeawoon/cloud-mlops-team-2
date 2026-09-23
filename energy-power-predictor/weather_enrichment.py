"""Download actual historical weather codes for a known house location.

Use only when the source data's latitude/longitude is known. Do not attach
Korean weather history to an overseas or unknown-location energy dataset.
"""
from __future__ import annotations
import argparse
import pandas as pd


def main(lat: float, lon: float, start: str, end: str, output: str) -> None:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
              "hourly": "weather_code,temperature_2m,relative_humidity_2m,precipitation", "timezone": "auto"}
    import urllib.parse, urllib.request, json
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=30) as response:
        hourly = json.load(response)["hourly"]
    pd.DataFrame(hourly).rename(columns={"time": "date"}).to_csv(output, index=False)
    print(f"saved {output}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--lat", type=float, required=True); p.add_argument("--lon", type=float, required=True)
    p.add_argument("--start", required=True); p.add_argument("--end", required=True); p.add_argument("--output", required=True)
    a = p.parse_args(); main(a.lat, a.lon, a.start, a.end, a.output)
