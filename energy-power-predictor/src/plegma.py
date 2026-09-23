"""Convert the Plegma household dataset to this project's hourly schema."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.features import (
    ADVANCED_FEATURE_COLUMNS,
    MANUAL_FEATURE_COLUMNS,
    WEATHER_SEVERITY,
    infer_weather,
)


def _calendar_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add features that are available at prediction time."""
    result = frame.copy()
    hour = result.index.hour
    weekday = result.index.weekday
    month = result.index.month
    result["temp_gap"] = result["indoor_temp_avg"] - result["T_out"]
    result["heating_need"] = (20 - result["indoor_temp_avg"]).clip(lower=0)
    result["cooling_need"] = (result["indoor_temp_avg"] - 24).clip(lower=0)
    result["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    result["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    result["weekday_sin"] = np.sin(2 * np.pi * weekday / 7)
    result["weekday_cos"] = np.cos(2 * np.pi * weekday / 7)
    result["month_sin"] = np.sin(2 * np.pi * month / 12)
    result["month_cos"] = np.cos(2 * np.pi * month / 12)
    result["is_weekend"] = (weekday >= 5).astype(int)
    result["weather_severity"] = infer_weather(result["T_out"], result["RH_out"]).map(WEATHER_SEVERITY)
    return result


def _load_house(house_dir: Path, defaults: dict[str, float], target_median_wh: float) -> pd.DataFrame:
    electric_files = sorted((house_dir / "Electric_data").glob("20*.csv"))
    environment_files = sorted((house_dir / "Environmental_data").glob("20*.csv"))
    if not electric_files or not environment_files:
        return pd.DataFrame()

    electric = pd.concat(
        [pd.read_csv(path, usecols=["timestamp", "P_agg"]) for path in electric_files],
        ignore_index=True,
    )
    electric["timestamp"] = pd.to_datetime(electric["timestamp"], errors="coerce")
    electric["P_agg"] = pd.to_numeric(electric["P_agg"], errors="coerce")
    # P_agg is average active power in W. W / 6 is equivalent to Wh per 10 min.
    hourly_power = electric.set_index("timestamp")["P_agg"].resample("1h").mean().rename("current_wh") / 6

    environment = pd.concat([pd.read_csv(path) for path in environment_files], ignore_index=True)
    environment["timestamp"] = pd.to_datetime(environment["timestamp"], errors="coerce")
    environment = environment.rename(columns={
        "internal_temperature": "indoor_temp_avg",
        "internal_humidity": "indoor_humidity_avg",
        "external_humidity": "RH_out",
    })
    # A few files use the corrected spelling while older ones use
    # ``external_temparature``. Coalesce both rather than creating duplicate
    # columns when monthly files are concatenated.
    typo_temperature = environment.get("external_temparature", pd.Series(np.nan, index=environment.index))
    corrected_temperature = environment.get("external_temperature", pd.Series(np.nan, index=environment.index))
    environment["T_out"] = typo_temperature.combine_first(corrected_temperature)
    hourly_environment = environment.set_index("timestamp")[["indoor_temp_avg", "indoor_humidity_avg", "T_out", "RH_out"]].resample("1h").mean()

    hourly = pd.concat([hourly_power, hourly_environment], axis=1).dropna()
    # Each monitored house has a different base load. Scale only the target and
    # history values to the UCI training household's median before pooling.
    # This preserves weather/time shape without letting a large home dominate.
    local_median = hourly["current_wh"].median()
    if not np.isfinite(local_median) or local_median <= 0:
        return pd.DataFrame()
    hourly["current_wh"] *= target_median_wh / local_median
    hourly["Windspeed"] = defaults["Windspeed"]
    hourly["Visibility"] = defaults["Visibility"]
    hourly["Press_mm_hg"] = defaults["Press_mm_hg"]
    hourly = _calendar_features(hourly)
    hourly["previous_hour_wh"] = hourly["current_wh"].shift(1)
    hourly["same_hour_yesterday_wh"] = hourly["current_wh"].shift(24)
    hourly["recent_3h_mean_wh"] = hourly["current_wh"].rolling(3).mean()
    hourly["next_hour_wh"] = hourly["current_wh"].shift(-1)

    # Do not form a target/lag across a recording gap.
    index_series = hourly.index.to_series()
    continuous_next = index_series.shift(-1).sub(index_series).eq(pd.Timedelta(hours=1))
    continuous_previous = index_series.sub(index_series.shift(1)).eq(pd.Timedelta(hours=1))
    continuous_yesterday = index_series.sub(index_series.shift(24)).eq(pd.Timedelta(hours=24))
    hourly = hourly.loc[continuous_next & continuous_previous & continuous_yesterday]
    return hourly.dropna(subset=ADVANCED_FEATURE_COLUMNS + ["next_hour_wh"])


def load_plegma_training_data(
    dataset_dir: str | Path, defaults: dict[str, float], target_median_wh: float,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load all usable Plegma homes in the same columns as the UCI model."""
    root = Path(dataset_dir) / "Clean_Dataset"
    homes = []
    for house_dir in sorted(root.glob("House_*")):
        house = _load_house(house_dir, defaults, target_median_wh)
        if not house.empty:
            homes.append(house)
    if not homes:
        raise ValueError(f"No usable Plegma files found under {root}")
    combined = pd.concat(homes, ignore_index=True)
    return combined, combined["next_hour_wh"]
