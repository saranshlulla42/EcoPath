"""
EcoPath — Unified Data Router

Every external source the frontend needs, proxied through one place. The
browser previously called GBIF and eBird directly, which put the eBird API key
in the client bundle, made responses uncacheable across users, and left the app
exposed to upstream CORS and rate-limit behaviour it could not control. The
Movebank proxy already solved this for one source; these routes generalise it.
"""

import logging
from typing import Optional

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile

from data import availability, cache
from data import repository as repo
from data.sources import ebird as ebird_source
from data.sources import gbif as gbif_source

logger = logging.getLogger("ecopath.data_router")
router = APIRouter()


def _payload(result) -> dict:
    """Envelope for the wire: data plus provenance, so the UI can attribute it."""
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error or "Upstream unavailable")
    return {"data": result.data, "provenance": result.provenance.as_dict()}


# ─── Health and introspection ────────────────────────────────────────────────

@router.get("/sources")
async def list_sources():
    """Which sources are configured and usable, plus cache effectiveness."""
    return {"sources": availability(), "cache": cache.stats()}


@router.delete("/cache")
async def clear_cache(source: str = Query("", description="Source id, or blank for all")):
    return {"cleared": cache.invalidate(source)}


# ─── Species ─────────────────────────────────────────────────────────────────

@router.get("/species/search")
async def search_species(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
):
    return _payload(await repo.search_species(q, limit=limit))


@router.get("/species/resolve")
async def resolve_species(name: str = Query(..., min_length=2)):
    return _payload(await repo.resolve_species(name))


@router.get("/species/{gbif_key}/media")
async def species_media(gbif_key: int, limit: int = Query(5, ge=1, le=20)):
    return _payload(await repo.species_images(gbif_key, limit=limit))


@router.get("/species/{gbif_key}/detail")
async def species_detail(gbif_key: int):
    return _payload(await gbif_source.species_detail(gbif_key))


# ─── Occurrences ─────────────────────────────────────────────────────────────

@router.get("/occurrences/{gbif_key}/points")
async def occurrence_points(
    gbif_key: int,
    year: int = Query(..., ge=1900, le=2100),
    limit: int = Query(300, ge=1, le=1000),
):
    """Georeferenced records for heatmaps — was a direct browser call to GBIF."""
    return _payload(await repo.heatmap_points(gbif_key, year, limit=limit))


@router.get("/occurrences/{gbif_key}/timeline")
async def occurrence_timeline(
    gbif_key: int,
    year_start: int = Query(2015, ge=1900, le=2100),
    year_end: int = Query(2024, ge=1900, le=2100),
    country: Optional[str] = Query("IN"),
):
    return _payload(await gbif_source.occurrence_counts_by_year(
        gbif_key, year_start, year_end, country=country or None))


# ─── eBird ───────────────────────────────────────────────────────────────────

@router.get("/ebird/observations/{species_code}")
async def ebird_recent(
    species_code: str,
    back: int = Query(30, ge=1, le=30),
    regions: Optional[str] = Query(None, description="Comma-separated region codes"),
):
    region_list = [r.strip() for r in regions.split(",") if r.strip()] if regions else None
    return _payload(await ebird_source.recent_observations(
        species_code, regions=region_list, back=back))


@router.get("/ebird/seasonal/{species_code}")
async def ebird_seasonal(species_code: str, year: int = Query(..., ge=1900, le=2100)):
    return _payload(await repo.seasonal_sightings(species_code, year))


@router.get("/ebird/taxonomy")
async def ebird_taxonomy(orders: Optional[str] = Query(None, description="Comma-separated orders")):
    order_list = [o.strip() for o in orders.split(",") if o.strip()] if orders else None
    return _payload(await ebird_source.taxonomy(orders=order_list))


@router.get("/ebird/species-list/{region_code}")
async def ebird_species_list(region_code: str):
    return _payload(await ebird_source.species_list(region_code))


# ─── Movement ────────────────────────────────────────────────────────────────

@router.get("/telemetry/studies")
async def telemetry_studies(taxon_name: str = Query(..., min_length=2)):
    return _payload(await repo.telemetry_studies(taxon_name))


@router.get("/telemetry/tracks")
async def telemetry_tracks(study_id: int = Query(...)):
    return _payload(await repo.telemetry_tracks(study_id))


# ─── Media ───────────────────────────────────────────────────────────────────

@router.get("/audio/recording/{recording_id}")
async def bird_call_audio(recording_id: str):
    result = await repo.bird_call_audio(recording_id)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error or "Audio unavailable")
    return Response(content=result.data, media_type="audio/mpeg")


@router.get("/audio/{scientific_name}")
async def bird_call(scientific_name: str, country: Optional[str] = Query("india")):
    return _payload(await repo.bird_call(scientific_name, country=country or None))


# ─── Environment ─────────────────────────────────────────────────────────────

@router.get("/weather")
async def weather(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    year: int = Query(..., ge=1940, le=2100),
):
    return _payload(await repo.weather(lat, lng, year))


# ─── Evidence ────────────────────────────────────────────────────────────────

@router.get("/evidence/status/{scientific_name}")
async def conservation_status(scientific_name: str):
    return _payload(await repo.conservation_status(scientific_name))


@router.get("/evidence/news")
async def news_evidence(
    q: str = Query(..., min_length=3),
    max_records: int = Query(6, ge=1, le=20),
    country: Optional[str] = Query(None),
):
    return _payload(await repo.news_evidence(q, max_records=max_records, country_code=country))


@router.get("/evidence/context/{scientific_name}")
async def species_context(scientific_name: str, common_name: str = Query("")):
    return _payload(await repo.species_context(scientific_name, common_name))


# ─── Vision ──────────────────────────────────────────────────────────────────

@router.post("/vision/identify")
async def identify_bird(image: UploadFile = File(...)):
    """
    Identify a bird from a photo and resolve it to a GBIF key.

    The browser used to call Gemini directly with NEXT_PUBLIC_GEMINI_API_KEY and
    then hit GBIF's match endpoint itself — duplicating logic the backend already
    had in `gemini_service.identify_bird_from_image`, and exposing the key.
    """
    from services.gemini_service import identify_bird_from_image

    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file is not an image")

    payload = await image.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    try:
        result = await identify_bird_from_image(payload, image.content_type or "image/jpeg")
    except Exception as e:
        logger.error(f"Vision identification failed: {e}")
        raise HTTPException(status_code=502, detail="Identification service unavailable") from e

    scientific_name = result.get("scientific_name") if result.get("is_bird") else None
    gbif_key = None
    if scientific_name:
        match = await gbif_source.match_species_key(scientific_name)
        gbif_key = match.data if match.ok else None

    return {
        "data": {**result, "scientific_name": scientific_name, "gbif_key": gbif_key},
        "provenance": {"source": "gemini+gbif", "operation": "identify_bird"},
    }
