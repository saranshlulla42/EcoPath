"""
eBird adapter.

eBird was previously called only from the browser, with the API key shipped in
the client bundle as NEXT_PUBLIC_EBIRD_API_KEY. Moving it server-side keeps the
key private, lets responses be cached across users instead of per-tab, and puts
the multi-region fan-out behind one bounded concurrency limit.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any, Optional

from data.envelope import Result, failed, ok
from data.http import fetch

# India first, then the flyway origins that feed Indian wintering grounds.
FLYWAY_REGIONS = ["IN", "LK", "NP", "BT", "BD", "MM", "RU", "CN"]


def normalize_observation(raw: dict) -> dict:
    """
    One raw eBird record in EcoPath's observation shape.

    A reported count of zero is meaningful — it records a survey that looked and
    found none — so it must survive normalisation rather than being coerced to
    the "unspecified count" default of 1.
    """
    count = raw.get("howMany")
    if not isinstance(count, (int, float)) or isinstance(count, bool):
        try:
            count = float(str(raw.get("howManyStr", "")).replace(",", ""))
        except (TypeError, ValueError):
            count = 1
    return {
        "lat": raw.get("lat") if isinstance(raw.get("lat"), (int, float)) else 0.0,
        "lng": raw.get("lng") if isinstance(raw.get("lng"), (int, float)) else 0.0,
        "date": raw.get("obsDt") or "",
        "count": count,
        "species_code": raw.get("speciesCode") or "",
        "species_name": raw.get("comName") or raw.get("sciName") or "Unknown",
        "location_name": raw.get("locName") or "Unknown",
    }


async def recent_observations(
    species_code: str, regions: Optional[list[str]] = None, back: int = 30,
) -> Result:
    """
    Recent sightings for a species across the flyway regions, deduplicated.

    Partial failure is normal here — a region with no records or a transient
    error should not lose the others, so results are gathered independently.
    """
    regions = regions or FLYWAY_REGIONS
    results = await asyncio.gather(*[
        fetch("ebird", "recent_observations", f"data/obs/{region}/recent/{species_code}",
              params={"back": back},
              headers={"X-eBirdApiToken": _key()})
        for region in regions
    ])

    if all(not r.ok for r in results):
        return failed("ebird", "recent_observations",
                      results[0].error or "all regions failed")

    seen, observations = set(), []
    for res in results:
        if not res.ok or not isinstance(res.data, list):
            continue
        for raw in res.data:
            key = (raw.get("speciesCode"), raw.get("lat"), raw.get("lng"), raw.get("obsDt"))
            if key in seen:
                continue
            seen.add(key)
            observations.append(normalize_observation(raw))

    degraded = any(not r.ok for r in results)
    return ok(observations, "ebird", "recent_observations",
              cached=all(r.provenance.cached for r in results),
              degraded=degraded,
              note="some regions unavailable" if degraded else None)


async def seasonal_observations(species_code: str, year: int, weeks: int = 52) -> Result:
    """Observations bucketed by ISO week, for migration timing."""
    jan1 = date(year, 1, 1)
    starts = [(w, (jan1 + timedelta(days=(w - 1) * 7)).isoformat()) for w in range(1, weeks + 1)]

    results = await asyncio.gather(*[
        fetch("ebird", "seasonal_observations", f"data/obs/world/historic/{start}",
              params={"species": species_code, "maxResults": 100},
              headers={"X-eBirdApiToken": _key()})
        for _, start in starts
    ])

    by_week: dict[int, list] = {}
    for (week, _), res in zip(starts, results):
        by_week[week] = [normalize_observation(r) for r in res.data] if (
            res.ok and isinstance(res.data, list)) else []

    return ok(by_week, "ebird", "seasonal_observations",
              degraded=any(not r.ok for r in results))


async def species_list(region_code: str) -> Result:
    return await fetch("ebird", "species_list", f"product/spplist/{region_code}",
                       headers={"X-eBirdApiToken": _key()}, ttl=24 * 3600)


async def taxonomy(orders: Optional[list[str]] = None) -> Result:
    """eBird taxonomy, optionally filtered to given taxonomic orders."""
    res = await fetch("ebird", "taxonomy", "ref/taxonomy/ebird",
                      params={"fmt": "json"}, headers={"X-eBirdApiToken": _key()},
                      ttl=30 * 24 * 3600)
    if not res.ok:
        return res
    items = [t for t in (res.data or []) if t.get("category") == "species"]
    if orders:
        wanted = {o.lower() for o in orders}
        items = [t for t in items if (t.get("order") or "").lower() in wanted]
    return ok([
        {"species_code": t.get("speciesCode"), "common_name": t.get("comName"),
         "scientific_name": t.get("sciName"), "order": t.get("order")}
        for t in items
    ], "ebird", "taxonomy", cached=res.provenance.cached)


def _key() -> str:
    from data.registry import get_source
    return get_source("ebird").key or ""
