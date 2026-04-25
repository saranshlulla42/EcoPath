"""
EcoPath — GBIF API Client
Fetches bird species and occurrence data from the Global Biodiversity
Information Facility (GBIF) API v1 with exponential-backoff retry.
"""

import asyncio
import logging
from typing import Any, Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from config import get_settings

logger = logging.getLogger("ecopath.gbif")
settings = get_settings()

GBIF_BASE = settings.gbif_base_url
AVES_KEY = settings.gbif_aves_taxon_key   # 212 = Class Aves
INDIA_CODE = settings.gbif_country_code   # "IN" for Indian inventory; empty = global


# ─── HTTP Client ─────────────────────────────────────────────────────────────
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "EcoPath/1.0 (ecological research dashboard)"},
        )
    return _client


# ─── Core Request with Retry ─────────────────────────────────────────────────
@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def _get(url: str, params: dict) -> dict:
    client = _get_client()
    resp = await client.get(url, params=params)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "10"))
        logger.warning(f"GBIF rate limited. Waiting {retry_after}s...")
        await asyncio.sleep(retry_after)
        resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


# ─── Species Search ───────────────────────────────────────────────────────────
async def search_species(query: str, limit: int = 10) -> list[dict]:
    """
    Fuzzy search for bird species by name.
    Returns list of matching GBIF species records.
    """
    data = await _get(
        f"{GBIF_BASE}/species/search",
        params={
            "q": query,
            "rank": "SPECIES",
            "higherTaxonKey": AVES_KEY,
            "status": "ACCEPTED",
            "limit": limit,
        },
    )
    return data.get("results", [])


async def get_species_by_key(gbif_key: int) -> Optional[dict]:
    """Fetch full taxonomic metadata for a species by GBIF key."""
    try:
        return await _get(f"{GBIF_BASE}/species/{gbif_key}", params={})
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return None
        raise


async def get_species_media(gbif_key: int, limit: int = 5) -> list[dict]:
    """Fetch media (images) for a species from GBIF."""
    data = await _get(
        f"{GBIF_BASE}/species/{gbif_key}/media",
        params={"limit": limit},
    )
    return data.get("results", [])


# ─── Indian Bird Species Inventory ───────────────────────────────────────────
async def fetch_indian_bird_species_keys(limit: int = 500) -> list[int]:
    """
    Fetch species keys for birds recorded in India.
    Uses occurrence faceting: country=IN, class=Aves.
    Returns a list of GBIF species keys.
    """
    logger.info(f"Fetching Indian bird species inventory (limit={limit})...")
    data = await _get(
        f"{GBIF_BASE}/occurrence/search",
        params={
            "taxonKey": AVES_KEY,
            "country": "IN",  # This function is always India-specific
            "limit": 0,
            "facet": "speciesKey",
            "facetLimit": limit,
            "hasCoordinate": "true",
            "hasGeospatialIssue": "false",
        },
    )
    facets = data.get("facets", [])
    species_keys = []
    for facet in facets:
        if facet.get("field") == "SPECIES_KEY":
            for item in facet.get("counts", []):
                try:
                    species_keys.append(int(item["name"]))
                except (KeyError, ValueError):
                    continue
    logger.info(f"Found {len(species_keys)} Indian bird species in GBIF")
    return species_keys


# ─── Occurrence Count by Year × State ─────────────────────────────────────────
async def get_occurrence_counts_by_year(
    gbif_species_key: int,
    start_year: int = 2015,
    end_year: int = 2024,
    country_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Fetch occurrence counts per year for a species.
    Pass country_code (ISO 3166-1 alpha-2) to filter by country, or omit for global data.
    Returns list of {year, count} dicts.
    """
    results = []
    for year in range(start_year, end_year + 1):
        try:
            params: dict[str, Any] = {
                "taxonKey": gbif_species_key,
                "year": year,
                "limit": 0,
                "hasCoordinate": "true",
                "hasGeospatialIssue": "false",
            }
            effective_country = country_code or INDIA_CODE
            if effective_country:
                params["country"] = effective_country
            data = await _get(f"{GBIF_BASE}/occurrence/search", params=params)
            results.append({
                "year": year,
                "count": data.get("count", 0),
            })
            # Polite delay to avoid rate limiting
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning(f"Failed to fetch count for key={gbif_species_key}, year={year}: {e}")
            results.append({"year": year, "count": 0})
    return results


async def get_occurrence_points(
    gbif_species_key: int,
    year: int,
    limit: int = 300,
    country_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    Fetch individual occurrence records with coordinates for heatmap.
    Pass country_code (ISO 3166-1 alpha-2) to filter by country, or omit for global data.
    Returns list of {lat, lng, year, stateProvince} dicts.
    """
    params: dict[str, Any] = {
        "taxonKey": gbif_species_key,
        "year": year,
        "limit": limit,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "fields": "decimalLatitude,decimalLongitude,stateProvince,year,month",
    }
    effective_country = country_code or INDIA_CODE
    if effective_country:
        params["country"] = effective_country
    data = await _get(f"{GBIF_BASE}/occurrence/search", params=params)
    points = []
    for r in data.get("results", []):
        lat = r.get("decimalLatitude")
        lng = r.get("decimalLongitude")
        if lat is not None and lng is not None:
            points.append({
                "lat": float(lat),
                "lng": float(lng),
                "state": r.get("stateProvince", "Unknown"),
                "year": r.get("year", year),
                "month": r.get("month"),
            })
    return points


# ─── xeno-canto: Bird Call Search ─────────────────────────────────────────────
async def fetch_bird_call(scientific_name: str, country: str = "India") -> Optional[dict]:
    """
    Search xeno-canto for the best quality recording of a species in India.
    Returns recording metadata with audio URL.
    """
    settings_obj = get_settings()
    query = f'{scientific_name} cnt:"{country}"'
    try:
        data = await _get(
            settings_obj.xenocanto_base_url,
            params={"query": query},
        )
        recordings = data.get("recordings", [])
        if not recordings:
            # Fallback: search without country filter
            data = await _get(
                settings_obj.xenocanto_base_url,
                params={"query": scientific_name},
            )
            recordings = data.get("recordings", [])

        if not recordings:
            return None

        # Sort by quality (A > B > C > D > E)
        quality_order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
        recordings.sort(key=lambda r: quality_order.get(r.get("q", "E"), 5))
        best = recordings[0]

        return {
            "id": best.get("id"),
            "species": best.get("en"),
            "common_name": best.get("en"),
            "country": best.get("cnt"),
            "location": best.get("loc"),
            "quality": best.get("q"),
            "duration": best.get("length"),
            "audio_url": f"https:{best.get('file')}" if best.get("file") else None,
            "sonogram_url": f"https:{best.get('sono', {}).get('small')}" if best.get("sono") else None,
            "recordist": best.get("rec"),
            "date": best.get("date"),
        }
    except Exception as e:
        logger.warning(f"xeno-canto fetch failed for {scientific_name}: {e}")
        return None
