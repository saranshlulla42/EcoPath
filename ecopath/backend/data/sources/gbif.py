"""
GBIF adapter.

GBIF was previously reached from five places — `services/gbif_client.py`, the
species and maps routers' fallbacks, four private fetchers inside the
extinction-risk service, and the browser directly via `frontend/lib/api.ts`.
Each shaped the response differently. This is now the only path.
"""

from __future__ import annotations

from typing import Any, Optional

from config import get_settings
from data.envelope import Result, ok
from data.http import fetch

settings = get_settings()
AVES = settings.gbif_aves_taxon_key

# GADM level-1 units for India, plus the two disputed territories GBIF files
# outside IND.* but still reports Indian occurrences under.
DISPUTED_GID_TO_STATE = {
    "Z01.14_1": "Jammu and Kashmir",
    "Z07.3_1": "Arunachal Pradesh",
}


async def search_species(query: str, limit: int = 10) -> Result:
    return await fetch("gbif", "search_species", "species/search",
                       params={"q": query, "rank": "SPECIES", "highertaxonKey": AVES,
                               "limit": limit, "status": "ACCEPTED"})


async def match_species_key(scientific_name: str) -> Result:
    """
    Resolve a scientific name to its accepted usage key.

    Hand-written species seeds carried unverified keys pointing at entirely
    different taxa, so name-matching is the only trustworthy way to get a key.
    """
    res = await fetch("gbif", "match_species", "species/match",
                      params={"name": scientific_name, "kingdom": "Animalia", "class": "Aves"},
                      ttl=7 * 24 * 3600)
    if not res.ok:
        return res
    data = res.data or {}
    key = None if data.get("matchType") in (None, "NONE") else (
        data.get("usageKey") or data.get("speciesKey")
    )
    return ok(key, "gbif", "match_species", cached=res.provenance.cached,
              upstream_url=res.provenance.upstream_url)


async def species_detail(gbif_key: int) -> Result:
    res = await fetch("gbif", "species_detail", f"species/{gbif_key}")
    if not res.ok:
        return res
    d = res.data or {}
    return ok({
        "gbif_key": gbif_key,
        "scientific_name": d.get("canonicalName") or d.get("scientificName"),
        "common_name": d.get("vernacularName"),
        "family": d.get("family"),
        "order_name": d.get("order"),
        "rank": d.get("rank"),
    }, "gbif", "species_detail", cached=res.provenance.cached)


async def species_media(gbif_key: int, limit: int = 5) -> Result:
    res = await fetch("gbif", "species_media", f"species/{gbif_key}/media",
                      params={"limit": limit})
    if not res.ok:
        return res
    items = [
        {"url": m.get("identifier"), "title": m.get("title"),
         "creator": m.get("creator"), "license": m.get("license")}
        for m in (res.data or {}).get("results", []) if m.get("identifier")
    ]
    return ok(items, "gbif", "species_media", cached=res.provenance.cached)


async def iucn_category(gbif_key: int) -> Result:
    res = await fetch("gbif", "iucn_category", f"species/{gbif_key}/iucnRedListCategory",
                      ttl=7 * 24 * 3600)
    return ok((res.data or {}).get("code") if res.ok else None,
              "gbif", "iucn_category", cached=res.provenance.cached)


async def occurrence_counts_by_year(
    gbif_key: int, start_year: int, end_year: int, country: Optional[str] = "IN",
) -> Result:
    """Exact yearly occurrence totals — one faceted request, not one per year."""
    params: dict[str, Any] = {
        "taxonKey": gbif_key, "year": f"{start_year},{end_year}", "limit": 0,
        "facet": "year", "facetLimit": 60, "facetMincount": 1,
        "hasCoordinate": "true", "hasGeospatialIssue": "false",
    }
    if country:
        params["country"] = country
    res = await fetch("gbif", "occurrence_counts_by_year", "occurrence/search", params=params)
    if not res.ok:
        return res
    counts = {}
    for facet in (res.data or {}).get("facets", []):
        if facet.get("field") == "YEAR":
            for item in facet.get("counts", []):
                try:
                    counts[int(item["name"])] = int(item["count"])
                except (KeyError, ValueError, TypeError):
                    continue
    series = [{"year": y, "count": counts.get(y, 0)} for y in range(start_year, end_year + 1)]
    return ok(series, "gbif", "occurrence_counts_by_year", cached=res.provenance.cached)


async def region_year_species_counts(gadm_gid: str, year: int, facet_limit: int = 1500) -> Result:
    """Every species recorded in one region-year, with exact totals."""
    res = await fetch("gbif", "region_year_species_counts", "occurrence/search", params={
        "taxonKey": AVES, "gadmGid": gadm_gid, "year": year, "limit": 0,
        "facet": "speciesKey", "facetLimit": facet_limit, "facetMincount": 1,
        "hasCoordinate": "true", "hasGeospatialIssue": "false",
    })
    if not res.ok:
        return res
    counts: dict[int, int] = {}
    for facet in (res.data or {}).get("facets", []):
        if facet.get("field") == "SPECIES_KEY":
            for item in facet.get("counts", []):
                try:
                    counts[int(item["name"])] = int(item["count"])
                except (KeyError, ValueError, TypeError):
                    continue
    return ok(counts, "gbif", "region_year_species_counts", cached=res.provenance.cached)


async def all_indian_bird_keys(start_year: int = 2015, end_year: int = 2024,
                               facet_limit: int = 1500) -> Result:
    res = await fetch("gbif", "all_indian_bird_keys", "occurrence/search", params={
        "taxonKey": AVES, "country": "IN", "year": f"{start_year},{end_year}", "limit": 0,
        "facet": "speciesKey", "facetLimit": facet_limit, "facetMincount": 1,
        "hasCoordinate": "true", "hasGeospatialIssue": "false",
    })
    if not res.ok:
        return res
    keys: dict[int, int] = {}
    for facet in (res.data or {}).get("facets", []):
        if facet.get("field") == "SPECIES_KEY":
            for item in facet.get("counts", []):
                try:
                    keys[int(item["name"])] = int(item["count"])
                except (KeyError, ValueError, TypeError):
                    continue
    return ok(keys, "gbif", "all_indian_bird_keys", cached=res.provenance.cached)


async def occurrence_month_facets(gbif_key: int, start_year: int, end_year: int,
                                  country: Optional[str] = "IN") -> Result:
    """
    Exact occurrence totals per calendar month across a year range.

    One faceted request. Used as the denominator for monthly coverage: the
    points fetched per month are a capped sample, so the true monthly total is
    what says whether a thin month is genuinely thin or merely under-sampled.
    """
    params: dict[str, Any] = {
        "taxonKey": gbif_key, "year": f"{start_year},{end_year}", "limit": 0,
        "facet": "month", "facetLimit": 12, "facetMincount": 1,
        "hasCoordinate": "true", "hasGeospatialIssue": "false",
    }
    if country:
        params["country"] = country
    res = await fetch("gbif", "occurrence_month_facets", "occurrence/search", params=params)
    if not res.ok:
        return res
    months: dict[int, int] = {}
    for facet in (res.data or {}).get("facets", []):
        if facet.get("field") != "MONTH":
            continue
        for item in facet.get("counts", []):
            try:
                months[int(item["name"])] = int(item["count"])
            except (KeyError, ValueError, TypeError):
                continue
    return ok(months, "gbif", "occurrence_month_facets", cached=res.provenance.cached)


async def occurrence_points(gbif_key: int, year: int | str, limit: int = 300,
                            country: Optional[str] = "IN",
                            month: Optional[int] = None) -> Result:
    """
    Individual georeferenced records, for heatmaps.

    `year` accepts a GBIF range string ("2015,2024") as well as a single year.
    `month` restricts to one calendar month, which is how the precompute job
    samples: GBIF returns records in a fixed order, so taking the first N of a
    whole year yields almost entirely January and makes any seasonal metric
    computed from it meaningless.
    """
    params: dict[str, Any] = {
        "taxonKey": gbif_key, "year": year, "limit": limit,
        "hasCoordinate": "true", "hasGeospatialIssue": "false",
    }
    if month is not None:
        params["month"] = month
    if country:
        params["country"] = country
    res = await fetch("gbif", "occurrence_points", "occurrence/search", params=params)
    if not res.ok:
        return res
    points = []
    for r in (res.data or {}).get("results", []):
        lat, lng = r.get("decimalLatitude"), r.get("decimalLongitude")
        if lat is None or lng is None:
            continue
        points.append({"lat": float(lat), "lng": float(lng), "year": r.get("year", year),
                       "month": r.get("month"), "state": r.get("stateProvince") or "Unknown"})
    return ok(points, "gbif", "occurrence_points", cached=res.provenance.cached)


async def gadm_subdivisions() -> Result:
    """GADM level-1 gid -> state name for India, including disputed territories."""
    res = await fetch("gbif", "gadm_subdivisions", "geocode/gadm/IND/subdivisions",
                      ttl=30 * 24 * 3600)
    mapping = {}
    if res.ok:
        for entry in res.data or []:
            if entry.get("id") and entry.get("name"):
                mapping[entry["id"]] = entry["name"]
    mapping.update(DISPUTED_GID_TO_STATE)
    return ok(mapping, "gbif", "gadm_subdivisions", cached=res.provenance.cached)


async def species_descriptions(gbif_key: int, limit: int = 12) -> Result:
    """Free-text description blocks (habitat, threats) attached to a taxon."""
    res = await fetch("gbif", "species_descriptions", f"species/{gbif_key}/descriptions",
                      params={"limit": limit})
    if not res.ok:
        return res
    return ok([
        {"type": d.get("type"), "description": d.get("description"), "source": d.get("source")}
        for d in (res.data or {}).get("results", []) if d.get("description")
    ], "gbif", "species_descriptions", cached=res.provenance.cached)


async def occurrence_country_facets(gbif_key: int, limit: int = 12,
                                    country: Optional[str] = None) -> Result:
    """Where a species is recorded, as country facet counts — a range summary."""
    params: dict[str, Any] = {
        "taxonKey": gbif_key, "limit": 0, "facet": "country",
        "facetLimit": limit, "facetMincount": 1,
    }
    if country:
        params["country"] = country
    res = await fetch("gbif", "occurrence_country_facets", "occurrence/search", params=params)
    if not res.ok:
        return res
    counts = []
    for facet in (res.data or {}).get("facets", []):
        if facet.get("field") == "COUNTRY":
            counts = [{"country": i.get("name"), "count": i.get("count")}
                      for i in facet.get("counts", [])]
    return ok(counts, "gbif", "occurrence_country_facets", cached=res.provenance.cached)
