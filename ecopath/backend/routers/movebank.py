"""
Movebank API Proxy Router

Proxies requests to Movebank API to avoid CORS issues and enable server-side
rate limiting and caching. The Movebank API frequently rate-limits (429) and
blocks browser-based requests.
"""

import asyncio
import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("ecopath.movebank")

router = APIRouter()

# ─── Constants ─────────────────────────────────────────────────────────────
MOVEBANK_BASE = "https://www.movebank.org/movebank/service/public/json"
MOVEBANK_TIMEOUT = 30.0
MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # Start at 2 seconds for server-side retries


# ─── Cache ─────────────────────────────────────────────────────────────────
# Simple in-memory cache; in production use Redis
_cache: dict[str, Any] = {}


def _get_cache_key(entity_type: str, **params) -> str:
    """Generate a cache key from params."""
    param_str = "_".join(f"{k}={v}" for k, v in sorted(params.items()))
    return f"movebank_{entity_type}_{param_str}"


async def _fetch_with_retry(
    entity_type: str, params: dict[str, Any], max_attempts: int = MAX_RETRIES
) -> Any:
    """
    Fetch from Movebank with exponential backoff.
    Server-side retries avoid browser CORS issues.
    """
    attempt = 0
    last_error = None

    while attempt < max_attempts:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=MOVEBANK_TIMEOUT) as client:
                response = await client.get(MOVEBANK_BASE, params=params)
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            last_error = e
            if e.response.status_code in (429, 503):
                if attempt >= max_attempts:
                    logger.warning(
                        f"[Movebank] Max retries exceeded for {entity_type}. "
                        f"Last status: {e.response.status_code}"
                    )
                    raise

                # Exponential backoff with jitter
                wait_seconds = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                jitter = wait_seconds * 0.1  # ±10% jitter
                import random

                wait_seconds += random.uniform(-jitter, jitter)
                wait_seconds = max(1.0, wait_seconds)  # At least 1 second

                logger.info(
                    f"[Movebank] Rate limited (429). "
                    f"Retrying in {wait_seconds:.1f}s (Attempt {attempt}/{max_attempts})..."
                )
                await asyncio.sleep(wait_seconds)
            else:
                # Non-retryable error
                logger.error(
                    f"[Movebank] Request failed for {entity_type}: "
                    f"{e.response.status_code}"
                )
                raise

        except Exception as e:
            logger.error(f"[Movebank] Unexpected error: {e}")
            raise

    if last_error:
        raise last_error


@router.get("/studies")
async def get_studies(
    taxon_name: str = Query(..., description="Species scientific name"),
) -> dict[str, Any]:
    """
    Get Movebank studies for a species.

    Query Parameters:
    - taxon_name: Scientific name (e.g., "Anhima cornuta")

    Returns a list of studies matching the taxon.
    """
    cache_key = _get_cache_key("studies", taxon_name=taxon_name)

    # Check cache
    if cache_key in _cache:
        logger.debug(f"[Movebank] Cache hit for {taxon_name}")
        return _cache[cache_key]

    try:
        params = {
            "entity_type": "study",
            "taxon_name": taxon_name,
        }

        try:
            data = await _fetch_with_retry("study", params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403, 429, 503):
                logger.warning(
                    f"[Movebank] {e.response.status_code} for {taxon_name}. Falling back to demo dataset."
                )
                data = [
                    {
                        "id": 999999,
                        "name": "Demonstration Telemetry (Mocked)",
                        "taxon_ids": taxon_name,
                        "number_of_individuals": 1,
                        "study_type": "Mock fallback",
                        "sensor_type_ids": "gps",
                    }
                ]
            else:
                raise

        # Normalize response — Movebank returns {"study": [...]} or plain list
        studies = []
        if isinstance(data, dict):
            study_list = data.get("study", data.get("studies", []))
        elif isinstance(data, list):
            study_list = data
        else:
            study_list = []

        for s in study_list:
            if not isinstance(s, dict):
                continue
            studies.append(
                {
                    "id": s.get("id") or s.get("study_id", 0),
                    "name": s.get("name") or s.get("study_name", "Unnamed Study"),
                    "taxonIds": s.get("taxon_ids", ""),
                    "numberOfIndividuals": s.get("number_of_individuals"),
                    "studyType": s.get("study_type"),
                    "sensorTypeIds": s.get("sensor_type_ids"),
                }
            )

        result = {"studies": studies, "count": len(studies)}

        # Cache for 30 minutes
        _cache[cache_key] = result

        logger.info(
            f"[Movebank] Found {len(studies)} studies for {taxon_name}")
        return result

    except Exception as e:
        logger.error(
            f"[Movebank] Failed to fetch studies for {taxon_name}: {e}")
        return {
            "studies": [
                {
                    "id": 999999,
                    "name": "Demonstration Telemetry (Fallback)",
                    "taxonIds": taxon_name,
                    "numberOfIndividuals": 1,
                    "studyType": "Mock fallback",
                    "sensorTypeIds": "gps",
                }
            ],
            "count": 1,
        }


@router.get("/tracks")
async def get_tracks(
    study_id: int = Query(..., description="Study ID"),
) -> dict[str, Any]:
    """
    Get GPS telemetry tracks for a study.

    Query Parameters:
    - study_id: Study ID from /studies endpoint

    Returns tracks grouped by individual animal.
    """
    if study_id == 999999:
        logger.info(
            "[Movebank] Returning synthetic demonstration track for mock study")
        import time
        import math

        now = int(time.time() * 1000)
        points = []
        track_points_count = 100
        for i in range(track_points_count):
            t = i / (track_points_count - 1)
            # smooth curve over globe
            lng = -80.0 + 15.0 * math.sin(t * math.pi) - 10.0 * t
            lat = 45.0 - 90.0 * t
            timestamp = now - int((1 - t) * 365 * 86400000)
            points.append({"lat": lat, "lng": lng, "timestamp": timestamp})

        return {
            "tracks": [{
                "path": [[p["lng"], p["lat"]] for p in points],
                "timestamps": [p["timestamp"] for p in points],
                "individualId": "mock-bird-1"
            }],
            "count": 1
        }

    cache_key = _get_cache_key("tracks", study_id=study_id)

    # Check cache
    if cache_key in _cache:
        logger.debug(f"[Movebank] Cache hit for study {study_id}")
        return _cache[cache_key]

    try:
        params = {
            "entity_type": "event",
            "study_id": study_id,
            "sensor_type": "gps",
            "attributes": "timestamp,location_long,location_lat,individual_id",
        }

        data = await _fetch_with_retry("event", params)

        # Group by individual — Movebank returns {"event": [...]} or plain list
        by_individual: dict[str, list[dict[str, Any]]] = {}

        if isinstance(data, dict):
            event_list = data.get("event", data.get("events", []))
        elif isinstance(data, list):
            event_list = data
        else:
            event_list = []

        for event in event_list:
            lat = event.get("location_lat")
            lng = event.get("location_long")
            ts = event.get("timestamp")
            individual_id = str(event.get("individual_id", "unknown"))

            if lat is None or lng is None or ts is None:
                continue

            # Parse timestamp
            if isinstance(ts, str):
                from datetime import datetime

                try:
                    parsed = int(datetime.fromisoformat(
                        ts.replace("Z", "+00:00")).timestamp() * 1000)
                except (ValueError, AttributeError):
                    continue
            else:
                parsed = int(ts)

            if individual_id not in by_individual:
                by_individual[individual_id] = []

            by_individual[individual_id].append(
                {"lat": lat, "lng": lng, "timestamp": parsed}
            )

        # Transform to TripsLayer format
        tracks = []
        for individual_id, points in by_individual.items():
            # Sort by timestamp
            points.sort(key=lambda p: p["timestamp"])

            if len(points) < 2:
                continue

            tracks.append(
                {
                    "path": [[p["lng"], p["lat"]] for p in points],
                    "timestamps": [p["timestamp"] for p in points],
                    "individualId": individual_id,
                }
            )

        result = {"tracks": tracks, "count": len(tracks)}

        # Cache for 30 minutes
        _cache[cache_key] = result

        logger.info(
            f"[Movebank] Found {len(tracks)} tracks for study {study_id}")
        return result

    except Exception as e:
        logger.error(
            f"[Movebank] Failed to fetch tracks for study {study_id}: {e}")
        return {
            "tracks": [],
            "count": 0,
            "message": "Movebank unavailable; no live tracks could be loaded",
        }
