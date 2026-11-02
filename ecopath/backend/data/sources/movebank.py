"""
Movebank adapter.

Movebank blocks browser-origin requests, so it was already proxied — but with a
private dict cache that never evicted and its own retry loop. The behaviour is
preserved (including the demonstration study used when Movebank refuses the
request) on top of the shared client and cache.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime
from typing import Any

from data.envelope import Result, ok
from data.http import fetch

logger = logging.getLogger("ecopath.data.movebank")

# Movebank returns 401/403 for studies whose licence has not been accepted.
# A synthetic study keeps the migration UI demonstrable rather than blank.
DEMO_STUDY_ID = 999999


async def studies(taxon_name: str) -> Result:
    res = await fetch("movebank", "studies", "",
                      params={"entity_type": "study", "taxon_name": taxon_name})

    if not res.ok:
        logger.warning(f"Movebank studies unavailable for {taxon_name}: {res.error}")
        return ok(_demo_studies(taxon_name), "movebank", "studies",
                  degraded=True, note=f"Movebank unavailable ({res.error}); demo study returned")

    raw = res.data
    items = raw.get("study", raw.get("studies", [])) if isinstance(raw, dict) else (
        raw if isinstance(raw, list) else [])

    normalized = [
        {
            "id": s.get("id") or s.get("study_id", 0),
            "name": s.get("name") or s.get("study_name", "Unnamed Study"),
            "taxonIds": s.get("taxon_ids", ""),
            "numberOfIndividuals": s.get("number_of_individuals"),
            "studyType": s.get("study_type"),
            "sensorTypeIds": s.get("sensor_type_ids"),
        }
        for s in items if isinstance(s, dict)
    ]
    if not normalized:
        return ok(_demo_studies(taxon_name), "movebank", "studies",
                  degraded=True, note="No public studies for this taxon; demo study returned")

    return ok(normalized, "movebank", "studies", cached=res.provenance.cached)


async def tracks(study_id: int) -> Result:
    if study_id == DEMO_STUDY_ID:
        return ok(_demo_track(), "movebank", "tracks",
                  degraded=True, note="Synthetic demonstration track")

    res = await fetch("movebank", "tracks", "", params={
        "entity_type": "event", "study_id": study_id, "sensor_type": "gps",
        "attributes": "timestamp,location_long,location_lat,individual_id",
    })
    if not res.ok:
        return ok([], "movebank", "tracks", degraded=True,
                  note=f"Movebank unavailable ({res.error}); no live tracks loaded")

    raw = res.data
    events = raw.get("event", raw.get("events", [])) if isinstance(raw, dict) else (
        raw if isinstance(raw, list) else [])

    by_individual: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        lat, lng, ts = event.get("location_lat"), event.get("location_long"), event.get("timestamp")
        if lat is None or lng is None or ts is None:
            continue
        parsed = _to_millis(ts)
        if parsed is None:
            continue
        by_individual.setdefault(str(event.get("individual_id", "unknown")), []).append(
            {"lat": lat, "lng": lng, "timestamp": parsed})

    result = []
    for individual_id, points in by_individual.items():
        points.sort(key=lambda p: p["timestamp"])
        if len(points) < 2:
            continue
        result.append({
            "path": [[p["lng"], p["lat"]] for p in points],
            "timestamps": [p["timestamp"] for p in points],
            "individualId": individual_id,
        })

    return ok(result, "movebank", "tracks", cached=res.provenance.cached)


def _to_millis(ts) -> int | None:
    if isinstance(ts, str):
        try:
            return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)
        except (ValueError, AttributeError):
            return None
    try:
        return int(ts)
    except (TypeError, ValueError):
        return None


def _demo_studies(taxon_name: str) -> list[dict]:
    return [{
        "id": DEMO_STUDY_ID, "name": "Demonstration Telemetry (Mocked)",
        "taxonIds": taxon_name, "numberOfIndividuals": 1,
        "studyType": "Mock fallback", "sensorTypeIds": "gps",
    }]


def _demo_track() -> list[dict]:
    now = int(time.time() * 1000)
    n = 100
    points = []
    for i in range(n):
        t = i / (n - 1)
        points.append({
            "lng": -80.0 + 15.0 * math.sin(t * math.pi) - 10.0 * t,
            "lat": 45.0 - 90.0 * t,
            "timestamp": now - int((1 - t) * 365 * 86400000),
        })
    return [{
        "path": [[p["lng"], p["lat"]] for p in points],
        "timestamps": [p["timestamp"] for p in points],
        "individualId": "mock-bird-1",
    }]
