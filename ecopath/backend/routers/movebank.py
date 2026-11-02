"""
EcoPath — Movebank Router (compatibility layer)

Movebank rejects browser-origin requests, so it has always been proxied. The
transport, retry, caching and demo-study fallback now live in
`data.sources.movebank`; these routes keep the original response shape for the
existing frontend. New clients should use `/api/data/telemetry/*`.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query

from data import repository as repo

logger = logging.getLogger("ecopath.movebank")
router = APIRouter()


@router.get("/studies")
async def get_studies(
    taxon_name: str = Query(..., description="Species scientific name"),
) -> dict[str, Any]:
    result = await repo.telemetry_studies(taxon_name)
    studies = result.data or []
    return {"studies": studies, "count": len(studies)}


@router.get("/tracks")
async def get_tracks(study_id: int = Query(..., description="Study ID")) -> dict[str, Any]:
    result = await repo.telemetry_tracks(study_id)
    tracks = result.data or []
    payload: dict[str, Any] = {"tracks": tracks, "count": len(tracks)}
    if result.provenance.degraded and not tracks:
        payload["message"] = result.provenance.note or "Movebank unavailable"
    return payload
