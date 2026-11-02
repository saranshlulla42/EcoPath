"""
EcoPath — Xeno-Canto Router (compatibility layer)

Keeps the API key server-side. Search, normalisation and audio proxying now
live in `data.sources.xenocanto`; new clients should use `/api/data/audio/*`.
"""

import logging

from fastapi import APIRouter, HTTPException, Path, Query, Response

from data import repository as repo
from data.sources import xenocanto as xc

logger = logging.getLogger("ecopath.xenocanto")
router = APIRouter()


@router.get("/")
async def proxy_xenocanto(
    query: str = Query(..., description='v3 search query, e.g. \'sp:"Pavo cristatus" cnt:india\''),
):
    result = await xc.search(query)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error or "xeno-canto unavailable")
    return result.data


@router.get("/audio/{recording_id}")
async def proxy_audio(recording_id: str = Path(..., description="Recording ID, e.g. '1085991'")):
    result = await repo.bird_call_audio(recording_id)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error or "Audio unavailable")
    return Response(content=result.data, media_type="audio/mpeg")
