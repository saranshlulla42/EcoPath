"""
EcoPath Backend — Xeno-Canto Proxy Router
Proxies requests to the Xeno-Canto v3 API to avoid browser CORS restrictions.
Also proxies audio file downloads since Xeno-Canto doesn't serve CORS headers
on its audio files, preventing browser <audio> elements from loading them.
Requires XENOCANTO_API_KEY in .env (get yours at https://xeno-canto.org/account).
"""

import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Query, HTTPException, Path
from fastapi.responses import StreamingResponse

from config import get_settings

logger = logging.getLogger("ecopath.xenocanto")

router = APIRouter(redirect_slashes=False)

XC_BASE = "https://xeno-canto.org/api/3/recordings"


@router.get("/")
async def proxy_xenocanto(query: str = Query(..., description="Xeno-Canto v3 search query using tags, e.g. 'sp:\"Pavo cristatus\"+cnt:india'")):
    """
    Proxy a Xeno-Canto v3 API call to bypass browser CORS.
    The backend appends its own API key so the frontend never needs it.
    Frontend sends: /api/xenocanto?query=sp:"Pavo cristatus"+cnt:india
    Backend fetches: https://xeno-canto.org/api/3/recordings?query=sp:"Pavo cristatus"+cnt:india&key=<KEY>
    """
    settings = get_settings()
    api_key = getattr(settings, "xenocanto_api_key", None) or ""

    url = f"{XC_BASE}?query={quote(query)}&key={api_key}"
    logger.info(
        f"Proxying Xeno-Canto v3 request: {XC_BASE}?query={quote(query)}&key=***")

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Xeno-Canto returned {e.response.status_code}: {e.response.text[:200]}")
            return {"recordings": [], "count": 0, "message": "Xeno-Canto unavailable"}
        except httpx.RequestError as e:
            logger.error(f"Xeno-Canto request failed: {e}")
            return {"recordings": [], "count": 0, "message": "Xeno-Canto unavailable"}


@router.get("/audio/{recording_id}")
async def proxy_audio(recording_id: str = Path(..., description="Xeno-Canto recording ID, e.g. '1085991'")):
    """
    Stream a Xeno-Canto audio file through the backend.
    Xeno-Canto doesn't serve Access-Control-Allow-Origin headers on its
    audio files, so the browser's <audio> element can't load them directly.
    This endpoint fetches the MP3 and streams it back with proper headers.
    """
    download_url = f"https://xeno-canto.org/{recording_id}/download"
    logger.info(f"Proxying Xeno-Canto audio: {download_url}")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            resp = await client.get(download_url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Xeno-Canto audio returned {e.response.status_code}")
            return StreamingResponse(iter([b""]), media_type="application/octet-stream")
        except httpx.RequestError as e:
            logger.error(f"Xeno-Canto audio request failed: {e}")
            return StreamingResponse(iter([b""]), media_type="application/octet-stream")

    content_type = resp.headers.get("content-type", "audio/mpeg")

    return StreamingResponse(
        iter([resp.content]),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=86400",
        },
    )
