"""
xeno-canto adapter (API v3).

Two independent paths existed: the `/api/xenocanto` proxy router and
`gbif_client.fetch_bird_call`, with different query syntax and neither caching.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from data.envelope import Result, ok
from data.http import fetch


async def search(query: str) -> Result:
    """Raw v3 search, e.g. 'sp:"Pavo cristatus" cnt:india'."""
    from data.registry import get_source
    return await fetch("xenocanto", "search", "",
                       params={"query": query, "key": get_source("xenocanto").key or ""})


async def bird_call(scientific_name: str, country: Optional[str] = "india") -> Result:
    """Best available recording for a species, normalised."""
    query = f'sp:"{scientific_name}"'
    if country:
        query += f" cnt:{country}"

    res = await search(query)
    recordings = (res.data or {}).get("recordings", []) if res.ok else []

    # A country filter can legitimately return nothing; retry worldwide before
    # reporting the species as having no recording at all.
    if not recordings and country:
        res = await search(f'sp:"{scientific_name}"')
        recordings = (res.data or {}).get("recordings", []) if res.ok else []
        if recordings:
            # Provenance is frozen; replace rather than mutate.
            res.provenance = replace(
                res.provenance, degraded=True,
                note=f"No recording from {country}; using a worldwide recording")

    if not res.ok:
        return res
    if not recordings:
        return ok(None, "xenocanto", "bird_call",
                  note=f"No xeno-canto recording found for {scientific_name}")

    best = recordings[0]
    return ok({
        "id": best.get("id"),
        "audio_url": best.get("file") or (best.get("sono") or {}).get("small"),
        "recordist": best.get("rec"),
        "location": best.get("loc"),
        "country": best.get("cnt"),
        "quality": best.get("q"),
        "license": best.get("lic"),
        "url": best.get("url"),
    }, "xenocanto", "bird_call", cached=res.provenance.cached)


async def audio_bytes(recording_id: str) -> Result:
    """
    Raw audio for one recording, proxied so the browser never needs a key.

    The download route lives outside the API base path, so it is requested as an
    absolute URL while still using the source's timeout and concurrency policy.
    Audio is not cached — the payloads are large and each is fetched once.
    """
    return await fetch(
        "xenocanto", "audio",
        f"https://xeno-canto.org/{recording_id}/download",
        parse="bytes", use_cache=False,
    )
