"""
EcoPath — Chat Router (RAG-powered Causal Reasoning Agent)
Implements Server-Sent Events (SSE) streaming with Gemini 2.5 Flash.

Species context is resolved via GBIF (not Supabase) to match
the frontend's direct-GBIF architecture.
"""

import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest
from services.gemini_service import stream_causal_reasoning
from services.weather_service import get_historical_weather

logger = logging.getLogger("ecopath.chat")
router = APIRouter()

GBIF_BASE = "https://api.gbif.org/v1"


async def _fetch_gbif_species(gbif_key_or_name: str) -> Optional[dict]:
    """
    Resolve a species from GBIF, either by numeric key or by name match.
    Returns a simplified species context dict.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try as numeric GBIF key first
            if gbif_key_or_name.isdigit():
                resp = await client.get(f"{GBIF_BASE}/species/{gbif_key_or_name}")
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "common_name": data.get("vernacularName") or data.get("canonicalName") or data.get("scientificName", "Unknown"),
                        "scientific_name": data.get("canonicalName") or data.get("scientificName", ""),
                        "iucn_status": data.get("threatStatus", "Unknown"),
                        "primary_habitat": [],
                        "primary_range": [],
                        "migratory": False,
                        "endemic_india": False,
                        "description": None,
                        "family": data.get("family", ""),
                        "order": data.get("order", ""),
                        "kingdom": data.get("kingdom", ""),
                    }

            # Fallback: try name-based match
            resp = await client.get(
                f"{GBIF_BASE}/species/match",
                params={"name": gbif_key_or_name, "kingdom": "Animalia"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("usageKey"):
                    return {
                        "common_name": data.get("canonicalName") or data.get("scientificName", "Unknown"),
                        "scientific_name": data.get("canonicalName") or data.get("scientificName", ""),
                        "iucn_status": "Unknown",
                        "primary_habitat": [],
                        "primary_range": [],
                        "migratory": False,
                        "endemic_india": False,
                        "description": None,
                        "family": data.get("family", ""),
                        "order": data.get("order", ""),
                    }
    except Exception as e:
        logger.warning(f"Failed to fetch GBIF species context for '{gbif_key_or_name}': {e}")

    return None


async def _build_rag_context(
    species_context_str: Optional[str],
    year_context: Optional[int],
) -> dict:
    """
    Build RAG context for the chat agent.
    Fetches species info from GBIF and weather data from Open-Meteo.
    """
    species_ctx = None
    weather_ctx = None

    if species_context_str:
        species_ctx = await _fetch_gbif_species(species_context_str)

        if species_ctx and year_context:
            # Fetch weather for India's central coordinates for that year
            try:
                weather_ctx = await get_historical_weather(
                    lat=22.0,
                    lng=78.5,
                    year=year_context,
                )
            except Exception:
                pass

    return {
        "species": species_ctx,
        "anomaly": None,  # Client-side anomaly detection — no Supabase dependency
        "weather": weather_ctx,
    }


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming SSE endpoint for the EcoPath Causal Reasoning Agent.
    Returns Server-Sent Events that the frontend reads incrementally.

    The agent:
    1. Retrieves species context from GBIF (RAG)
    2. Fetches weather data for the context year (if applicable)
    3. Streams a Gemini 2.5 Flash causal hypothesis token-by-token
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    async def event_generator():
        try:
            # Tell the client that we established connection and are retrieving data
            if request.species_context or request.year_context:
                yield f"data: {json.dumps({'delta': '⏳ *Retrieving ecological context...*\n\n', 'done': False})}\n\n"

            # Build RAG context (GBIF-based, no Supabase) - moved inside generator so headers are sent immediately
            ctx = await _build_rag_context(
                request.species_context,
                request.year_context,
            )

            if request.species_context or request.year_context:
                yield f"data: {json.dumps({'delta': '🧠 *Analyzing data with Gemini 2.5...*\n\n---\n\n', 'done': False})}\n\n"

            async for token in stream_causal_reasoning(
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
                species_context=ctx["species"],
                anomaly_context=ctx["anomaly"],
                weather_context=ctx["weather"],
            ):
                # SSE format: data: {json}\n\n
                payload = json.dumps({"delta": token, "done": False})
                yield f"data: {payload}\n\n"

            # Send done signal
            done_payload = json.dumps({"delta": "", "done": True})
            yield f"data: {done_payload}\n\n"

        except Exception as e:
            logger.error(f"Chat stream error: {e}")
            error_payload = json.dumps({
                "delta": f"\n\n⚠️ An error occurred: {str(e)}",
                "done": True,
            })
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/")
async def chat_non_streaming(request: ChatRequest):
    """
    Non-streaming fallback chat endpoint.
    Collects the full Gemini response and returns at once.
    """
    ctx = await _build_rag_context(
        request.species_context,
        request.year_context,
    )

    full_response = []
    async for token in stream_causal_reasoning(
        messages=[{"role": m.role, "content": m.content} for m in request.messages],
        species_context=ctx["species"],
        anomaly_context=ctx["anomaly"],
        weather_context=ctx["weather"],
    ):
        full_response.append(token)

    return {
        "role": "assistant",
        "content": "".join(full_response),
    }
