"""Estimate the incremental Korean residential electricity charge.

This is an estimate of the extra charge for predicted use. It excludes the
already-incurred monthly basic charge, discounts, TV licence fee and rounding.
"""
from __future__ import annotations

RATES = {
    "주택용 저압": [59.1, 122.6, 183.0, 273.2, 406.7, 690.8],
    "주택용 고압": [56.1, 96.3, 143.4, 209.9, 317.1, 559.5],
}


def energy_charge(usage_kwh: float, tariff: str) -> float:
    rates = RATES[tariff]
    remaining, total = max(usage_kwh, 0), 0.0
    for index, rate in enumerate(rates):
        block = remaining if index == len(rates) - 1 else min(remaining, 100)
        total += block * rate
        remaining -= block
        if remaining <= 0:
            break
    return total


def estimate_incremental_cost(current_kwh: float, added_kwh: float, tariff: str) -> tuple[float, float]:
    """Return energy-only and tax/fund-inclusive incremental estimates in KRW."""
    energy_only = energy_charge(current_kwh + added_kwh, tariff) - energy_charge(current_kwh, tariff)
    return energy_only, energy_only * 1.137  # VAT 10% + power-industry fund 3.7%
