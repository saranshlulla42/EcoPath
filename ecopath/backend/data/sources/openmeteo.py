"""
Open-Meteo adapter — historical weather archive.

Past years never change, so these responses cache for a week rather than the
default hour. Anomaly correlation asks for the same decade of a state's weather
on every request; without a long TTL that was ten uncached calls each time.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from data.envelope import Result, ok
from data.http import fetch

DAILY_FIELDS = [
    "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
    "rain_sum", "snowfall_sum", "wind_speed_10m_max",
]

# Indian monsoon runs June-September; day-of-year 151-273.
MONSOON_START, MONSOON_END = 151, 274


async def historical_year(lat: float, lng: float, year: int) -> Result:
    res = await fetch("openmeteo", "historical_year", "", params={
        "latitude": lat, "longitude": lng,
        "start_date": f"{year}-01-01", "end_date": f"{year}-12-31",
        "daily": ",".join(DAILY_FIELDS), "timezone": "Asia/Kolkata",
    })
    if not res.ok:
        return res

    daily = (res.data or {}).get("daily", {})
    temps_max = daily.get("temperature_2m_max", []) or []
    temps_min = daily.get("temperature_2m_min", []) or []
    precip = daily.get("precipitation_sum", []) or []

    return ok({
        "year": year,
        "location": {"lat": lat, "lng": lng},
        "annual_avg_temp_max": _avg(temps_max),
        "annual_avg_temp_min": _avg(temps_min),
        "annual_precipitation_mm": _sum(precip),
        "monsoon_precipitation_mm": _sum(precip[MONSOON_START:MONSOON_END]),
        "extreme_heat_days_gt40c": sum(1 for t in temps_max if t is not None and t > 40),
        "dry_days_count": sum(1 for p in precip if p is not None and p < 1),
    }, "openmeteo", "historical_year", cached=res.provenance.cached)


async def historical_years(lat: float, lng: float, years: list[int]) -> Result:
    """Several years at once. A year that fails is omitted, not fatal."""
    results = await asyncio.gather(*[historical_year(lat, lng, y) for y in years])
    by_year = {y: r.data for y, r in zip(years, results) if r.ok and r.data}
    return ok(by_year, "openmeteo", "historical_years",
              degraded=any(not r.ok for r in results),
              note=None if all(r.ok for r in results) else "some years unavailable")


def _avg(values: list) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _sum(values: list) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return round(sum(clean), 2) if clean else None
