"""
EcoPath — Precomputed migration data.

Serves the Stage 4 DuckDB store so the command bar and the migration map can
answer without touching GBIF at request time.

Everything here is observation density, never abundance: `n_points` counts
records, which track observer effort as much as bird presence.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from precompute import read

logger = logging.getLogger("ecopath.precompute_router")
router = APIRouter()


def _resolve(scientific_name: str) -> str:
    species_id = read.species_id_for(scientific_name)
    if not species_id:
        # Not analysed is not the same as not migratory, and the caller must be
        # able to tell them apart.
        raise HTTPException(status_code=404, detail="Species has not been precomputed")
    return species_id


@router.get("/status")
async def get_status(sci: str = Query(..., description="Scientific name")) -> dict:
    """Three-state migration status with its coverage evidence."""
    species_id = _resolve(sci)
    status = read.status_for(species_id)
    if not status:
        raise HTTPException(status_code=404, detail="No status computed for this species")
    return {"species_id": species_id, **status}


@router.get("/track")
async def get_track(sci: str = Query(...)) -> dict:
    """Monthly centroids. Months with no data are absent, not interpolated."""
    species_id = _resolve(sci)
    return {"species_id": species_id, "months": read.monthly_track(species_id)}


@router.get("/hexes")
async def get_hexes(
    sci: str = Query(...),
    month: int = Query(..., ge=1, le=12),
    resolution: Optional[int] = Query(None, ge=0, le=9),
) -> dict:
    """H3 observation-density cells for one month, as GeoJSON."""
    species_id = _resolve(sci)
    return read.month_hexes_geojson(species_id, month, resolution)
