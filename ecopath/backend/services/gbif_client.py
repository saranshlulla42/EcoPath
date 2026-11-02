"""
EcoPath — GBIF Client (compatibility shim)

The GBIF implementation now lives in `data.sources.gbif`, behind the shared
HTTP client, retry policy and cache. GBIF used to be reached from five places
with five different response shapes; this module remains only so existing
imports keep working.

New code should call `data.repository` for domain operations, or
`data.sources.gbif` when it genuinely needs a GBIF-specific call.
"""

import logging
from typing import Any, Optional

from data.sources import gbif as _gbif
from data.sources import xenocanto as _xenocanto

logger = logging.getLogger("ecopath.gbif")


async def search_species(query: str, limit: int = 10) -> list[dict]:
    res = await _gbif.search_species(query, limit)
    return (res.data or {}).get("results", []) if res.ok else []


async def get_species_by_key(gbif_key: int) -> Optional[dict]:
    res = await _gbif.species_detail(gbif_key)
    return res.data if res.ok else None


async def get_species_media(gbif_key: int, limit: int = 5) -> list[dict]:
    res = await _gbif.species_media(gbif_key, limit)
    return res.data if res.ok else []


async def match_species_key(scientific_name: str) -> Optional[int]:
    res = await _gbif.match_species_key(scientific_name)
    return res.data if res.ok else None


async def fetch_species_detail(gbif_key: int) -> Optional[dict[str, Any]]:
    res = await _gbif.species_detail(gbif_key)
    return res.data if res.ok else None


async def fetch_iucn_category(gbif_key: int) -> Optional[str]:
    res = await _gbif.iucn_category(gbif_key)
    return res.data if res.ok else None


async def fetch_gadm_subdivisions() -> dict[str, str]:
    res = await _gbif.gadm_subdivisions()
    return res.data or {}


async def fetch_region_year_species_counts(
    gadm_gid: str, year: int, facet_limit: int = 1500,
) -> dict[int, int]:
    res = await _gbif.region_year_species_counts(gadm_gid, year, facet_limit)
    return res.data or {}


async def fetch_all_indian_bird_keys(
    start_year: int = 2015, end_year: int = 2024, facet_limit: int = 1500,
) -> dict[int, int]:
    res = await _gbif.all_indian_bird_keys(start_year, end_year, facet_limit)
    return res.data or {}


async def fetch_indian_bird_species_keys(limit: int = 500) -> list[int]:
    res = await _gbif.all_indian_bird_keys(facet_limit=limit)
    return list((res.data or {}).keys())[:limit]


async def get_occurrence_counts_by_year(
    gbif_species_key: int, start_year: int = 2015, end_year: int = 2024,
    country_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    res = await _gbif.occurrence_counts_by_year(
        gbif_species_key, start_year, end_year, country=country_code or "IN")
    return res.data if res.ok else []


async def get_occurrence_points(
    gbif_species_key: int, year: int, limit: int = 300,
    country_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    res = await _gbif.occurrence_points(
        gbif_species_key, year, limit=limit, country=country_code or "IN")
    return res.data if res.ok else []


async def fetch_bird_call(scientific_name: str, country: str = "India") -> Optional[dict]:
    res = await _xenocanto.bird_call(scientific_name, country=country.lower() if country else None)
    return res.data if res.ok else None


# Re-exported so the ingestor's disputed-territory mapping keeps working.
DISPUTED_GID_TO_STATE = _gbif.DISPUTED_GID_TO_STATE
