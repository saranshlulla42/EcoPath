"""
EcoPath — Weather Service (compatibility shim)

The Open-Meteo implementation now lives in `data.sources.openmeteo`, behind the
shared HTTP client and cache. This module remains so existing imports keep
working; new code should call `data.repository.weather` directly.
"""

import logging
from typing import Any, Optional

from data import repository as repo

logger = logging.getLogger("ecopath.weather")


async def get_historical_weather(lat: float, lng: float, year: int) -> Optional[dict[str, Any]]:
    """Annual weather summary for a location. Returns None when unavailable."""
    result = await repo.weather(lat, lng, year)
    if not result.ok or not result.data:
        logger.warning(f"Weather unavailable for ({lat},{lng}) {year}: {result.error}")
        return None
    # Callers expect the source label that the old implementation appended.
    return {**result.data, "data_source": "Open-Meteo Historical Archive"}


async def get_multi_year_weather_summary(
    lat: float, lng: float, years: list[int],
) -> dict[int, dict[str, Any]]:
    result = await repo.weather_years(lat, lng, years)
    return {
        year: {**payload, "data_source": "Open-Meteo Historical Archive"}
        for year, payload in (result.data or {}).items()
    }
