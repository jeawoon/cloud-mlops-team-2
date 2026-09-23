"""Feature engineering for next-hour household energy forecasting."""
from __future__ import annotations

import numpy as np
import pandas as pd

WEATHER_SEVERITY = {"맑음": 0, "흐림": 1, "비": 2, "눈": 3}
MANUAL_FEATURE_COLUMNS = ["indoor_temp_avg", "indoor_humidity_avg", "T_out", "RH_out", "Windspeed", "Visibility", "Press_mm_hg", "temp_gap", "heating_need", "cooling_need", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos", "month_sin", "month_cos", "is_weekend", "weather_severity"]
ADVANCED_FEATURE_COLUMNS = MANUAL_FEATURE_COLUMNS + ["previous_hour_wh", "same_hour_yesterday_wh", "recent_3h_mean_wh"]


def infer_weather(t_out: pd.Series, rh_out: pd.Series) -> pd.Series:
    conditions = np.select([(t_out <= 1) & (rh_out >= 90), rh_out >= 92, rh_out >= 75], ["눈", "비", "흐림"], default="맑음")
    return pd.Series(conditions, index=t_out.index, name="weather")


def make_hourly_training_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Predict next hour's average use from the current hour's conditions."""
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"])
    hourly = df.set_index("date").sort_index().resample("1h").mean(numeric_only=True).dropna()
    hourly["indoor_temp_avg"] = hourly[[f"T{i}" for i in range(1, 10)]].mean(axis=1)
    hourly["indoor_humidity_avg"] = hourly[[f"RH_{i}" for i in range(1, 10)]].mean(axis=1)
    hourly["temp_gap"] = hourly["indoor_temp_avg"] - hourly["T_out"]
    hourly["heating_need"] = (20 - hourly["indoor_temp_avg"]).clip(lower=0)
    hourly["cooling_need"] = (hourly["indoor_temp_avg"] - 24).clip(lower=0)
    hour, weekday, month = hourly.index.hour, hourly.index.weekday, hourly.index.month
    hourly["hour_sin"], hourly["hour_cos"] = np.sin(2 * np.pi * hour / 24), np.cos(2 * np.pi * hour / 24)
    hourly["weekday_sin"], hourly["weekday_cos"] = np.sin(2 * np.pi * weekday / 7), np.cos(2 * np.pi * weekday / 7)
    hourly["month_sin"], hourly["month_cos"] = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)
    hourly["is_weekend"] = (weekday >= 5).astype(int)
    hourly["weather_severity"] = infer_weather(hourly["T_out"], hourly["RH_out"]).map(WEATHER_SEVERITY)
    # These values are available at prediction time and capture household routines.
    hourly["previous_hour_wh"] = hourly["Appliances"]
    hourly["same_hour_yesterday_wh"] = hourly["Appliances"].shift(24)
    hourly["recent_3h_mean_wh"] = hourly["Appliances"].rolling(3).mean()
    hourly["next_hour_wh"] = hourly["Appliances"].shift(-1)
    hourly = hourly.dropna(subset=["next_hour_wh", "same_hour_yesterday_wh", "recent_3h_mean_wh"])
    return hourly, hourly["next_hour_wh"]


def make_demo_row(indoor_temp: float, indoor_humidity: float, outdoor_temp: float, outdoor_humidity: float, weather: str, hour: int, weekday: int, month: int, defaults: dict[str, float], previous_hour_wh: float | None = None, same_hour_yesterday_wh: float | None = None, recent_3h_mean_wh: float | None = None) -> pd.DataFrame:
    row = {
        "indoor_temp_avg": indoor_temp, "indoor_humidity_avg": indoor_humidity, "T_out": outdoor_temp, "RH_out": outdoor_humidity,
        "Windspeed": defaults["Windspeed"] + (1.3 if weather in {"비", "눈"} else 0),
        "Visibility": max(1, defaults["Visibility"] - (12 if weather in {"비", "눈"} else 5 if weather == "흐림" else 0)),
        "Press_mm_hg": defaults["Press_mm_hg"], "temp_gap": indoor_temp - outdoor_temp,
        "heating_need": max(0, 20 - indoor_temp), "cooling_need": max(0, indoor_temp - 24),
        "hour_sin": np.sin(2 * np.pi * hour / 24), "hour_cos": np.cos(2 * np.pi * hour / 24),
        "weekday_sin": np.sin(2 * np.pi * weekday / 7), "weekday_cos": np.cos(2 * np.pi * weekday / 7),
        "month_sin": np.sin(2 * np.pi * month / 12), "month_cos": np.cos(2 * np.pi * month / 12),
        "is_weekend": int(weekday >= 5), "weather_severity": WEATHER_SEVERITY[weather],
    }
    if previous_hour_wh is not None and same_hour_yesterday_wh is not None and recent_3h_mean_wh is not None:
        row["previous_hour_wh"] = previous_hour_wh
        row["same_hour_yesterday_wh"] = same_hour_yesterday_wh
        row["recent_3h_mean_wh"] = recent_3h_mean_wh
        return pd.DataFrame([row], columns=ADVANCED_FEATURE_COLUMNS)
    return pd.DataFrame([row], columns=MANUAL_FEATURE_COLUMNS)
