"""
EcoPath — Open-Meteo Historical Weather Service
Fetches historical weather data for anomaly context enrichment.
"""

import logging
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import get_settings

logger = logging.getLogger("ecopath.weather")
settings = get_settings()


@retry(
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def get_historical_weather(
    lat: float,
    lng: float,
    year: int,
) -> Optional[dict[str, Any]]:
    """
    Fetch annual weather summary for a location and year using Open-Meteo
    historical archive API. No key required.

    Returns a contextual weather snapshot: temperature, precipitation,
    drought events useful for causal anomaly reasoning.
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": start_date,
        "end_date": end_date,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "rain_sum",
            "snowfall_sum",
            "wind_speed_10m_max",
        ],
        "timezone": "Asia/Kolkata",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(settings.openmeteo_base_url, params=params)
            resp.raise_for_status()
            data = resp.json()

        daily = data.get("daily", {})
        temps_max = daily.get("temperature_2m_max", [])
        temps_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        rain = daily.get("rain_sum", [])

        # Summarize into seasonal buckets (Indian seasons)
        def safe_avg(lst):
            clean = [v for v in lst if v is not None]
            return round(sum(clean) / len(clean), 2) if clean else None

        def safe_sum(lst):
            clean = [v for v in lst if v is not None]
            return round(sum(clean), 2) if clean else None

        # Monsoon: June–September (indices 151–273)
        monsoon_precip = safe_sum(precip[151:274])

        # Count extreme heat days (>40°C)
        extreme_heat_days = sum(1 for t in temps_max if t is not None and t > 40)

        # Count dry days (precipitation < 1mm)
        dry_days = sum(1 for p in precip if p is not None and p < 1)

        return {
            "year": year,
            "location": {"lat": lat, "lng": lng},
            "annual_avg_temp_max": safe_avg(temps_max),
            "annual_avg_temp_min": safe_avg(temps_min),
            "annual_precipitation_mm": safe_sum(precip),
            "monsoon_precipitation_mm": monsoon_precip,
            "extreme_heat_days_gt40c": extreme_heat_days,
            "dry_days_count": dry_days,
            "data_source": "Open-Meteo Historical Archive",
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Open-Meteo API error for ({lat},{lng}) year={year}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching weather: {e}")
        return None


async def get_multi_year_weather_summary(
    lat: float,
    lng: float,
    years: list[int],
) -> dict[int, dict[str, Any]]:
    """Fetch weather summaries for multiple years. Used for anomaly context."""
    import asyncio
    tasks = [get_historical_weather(lat, lng, year) for year in years]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        year: result
        for year, result in zip(years, results)
        if result and not isinstance(result, Exception)
    }
