"""
EcoPath — Species Router
Handles species search, detail fetch, and vision-based identification.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import JSONResponse

from models.schemas import (
    SpeciesSearchResult,
    SpeciesDetail,
    VisionIDResponse,
    PopulationYearSummary,
)
from services.supabase_client import get_supabase
from services.gbif_client import search_species, fetch_bird_call
from services.gemini_service import identify_bird_from_image, generate_ecology_answers

logger = logging.getLogger("ecopath.species")
router = APIRouter()


@router.get("", response_model=list[SpeciesSearchResult])
async def list_species(limit: int = Query(20, ge=1, le=100)):
    """
    List seeded species from the database default view.
    """
    supabase = get_supabase()
    result = (
        supabase.table("species")
        .select("id, common_name, scientific_name, family, iucn_status, image_url, gbif_image_url, endemic_india, migratory")
        .limit(limit)
        .execute()
    )
    return result.data or []


@router.get("/search", response_model=list[SpeciesSearchResult])
async def search_species_endpoint(
    q: str = Query(..., min_length=2,
                   description="Search query (common or scientific name)"),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Fuzzy-search species by name using trigram index.
    Falls back to GBIF API if local DB result count is low.
    """
    supabase = get_supabase()

    # Try local DB first (fast path)
    result = (
        supabase.table("species")
        .select("id, common_name, scientific_name, family, iucn_status, image_url, gbif_image_url, endemic_india, migratory")
        .ilike("common_name", f"%{q}%")
        .limit(limit)
        .execute()
    )

    species_list = result.data or []

    # If too few local results, supplement with GBIF
    if len(species_list) < 3:
        try:
            gbif_results = await search_species(q, limit=limit)
            gbif_formatted = []
            for r in gbif_results:
                if r.get("rank") == "SPECIES" and r.get("kingdom") == "Animalia":
                    gbif_formatted.append({
                        "id": None,
                        "common_name": r.get("vernacularName") or r.get("canonicalName", "Unknown"),
                        "scientific_name": r.get("canonicalName", ""),
                        "family": r.get("family"),
                        "iucn_status": None,
                        "image_url": None,
                        "gbif_image_url": None,
                        "endemic_india": False,
                        "migratory": False,
                    })
            existing_names = {s["scientific_name"] for s in species_list}
            for g in gbif_formatted:
                if g["scientific_name"] not in existing_names:
                    species_list.append(g)
        except Exception as e:
            logger.warning(f"GBIF supplement search failed for {q}: {e}")

    return species_list[:limit]


@router.get("/{species_id}", response_model=SpeciesDetail)
async def get_species_detail(species_id: UUID):
    """
    Full species detail including population history, anomalies,
    migration routes, and xeno-canto bird call.
    """
    supabase = get_supabase()

    # Fetch species
    result = (
        supabase.table("species")
        .select("*")
        .eq("id", str(species_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Species not found")

    species = result.data

    # Fetch population history
    pop_result = (
        supabase.rpc("get_yearly_totals", {"p_species_id": str(species_id)})
        .execute()
    )
    population_history = [
        PopulationYearSummary(
            year=row["year"],
            total_observations=row["total_count"],
            states_observed=row["state_count"],
        )
        for row in (pop_result.data or [])
    ]

    # Fetch anomalies
    anomaly_result = (
        supabase.table("anomalies")
        .select("*")
        .eq("species_id", str(species_id))
        .order("year", desc=True)
        .execute()
    )

    # Fetch migration routes
    migration_result = (
        supabase.table("migration_routes")
        .select("id, species_id, route_name, flyway, season, direction, waypoints, active_months, distance_km")
        .eq("species_id", str(species_id))
        .execute()
    )

    # Fetch xeno-canto recording if not cached
    xeno_recording = None
    if not species.get("xeno_canto_id"):
        try:
            xeno_data = await fetch_bird_call(species["scientific_name"])
            if xeno_data and xeno_data.get("audio_url"):
                xeno_recording = xeno_data
                # Cache the xeno-canto ID in DB
                supabase.table("species").update(
                    {"xeno_canto_id": xeno_data.get("id")}
                ).eq("id", str(species_id)).execute()
        except Exception as e:
            logger.warning(f"xeno-canto fetch skipped: {e}")

    return {
        **species,
        "population_history": population_history,
        "anomalies": anomaly_result.data or [],
        "migration_routes": migration_result.data or [],
        "xeno_canto_recording": xeno_recording,
    }


@router.post("/identify", response_model=VisionIDResponse)
async def identify_species_from_image(
    file: UploadFile = File(..., description="Bird photo to identify"),
):
    """
    Identify a bird species from an uploaded photo using Gemini Flash.
    Includes spoof detection (rejects drawings, screenshots, paintings).
    Max file size: 10MB.
    """
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image format. Use JPEG, PNG, or WebP.",
        )

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=400, detail="Image too large. Maximum 10MB.")

    # Gemini Flash vision identification
    try:
        result = await identify_bird_from_image(content, file.content_type)
    except Exception as e:
        logger.warning(f"Vision ID failed for upload {file.filename}: {e}")
        result = {
            "identified": False,
            "common_name": None,
            "scientific_name": None,
            "confidence": 0.0,
            "is_bird": False,
            "is_real_photo": False,
            "spoof_warning": "Vision model unavailable.",
            "reasoning": "The local vision service could not complete the identification.",
        }

    # Try to match identified species to our database
    matched_species = None
    if result.get("identified") and result.get("scientific_name"):
        supabase = get_supabase()
        match = (
            supabase.table("species")
            .select("id, common_name, scientific_name, family, iucn_status, image_url, gbif_image_url, endemic_india, migratory")
            .ilike("scientific_name", f"%{result['scientific_name'].split()[0]}%")
            .limit(1)
            .execute()
        )
        if match.data:
            matched_species = match.data[0]

    return VisionIDResponse(
        identified=result.get("identified", False),
        common_name=result.get("common_name"),
        scientific_name=result.get("scientific_name"),
        confidence=float(result.get("confidence", 0.0)),
        is_bird=result.get("is_bird", False),
        is_real_photo=result.get("is_real_photo", True),
        spoof_warning=result.get("spoof_warning"),
        matched_species=matched_species,
        reasoning=result.get("reasoning", ""),
    )


@router.get("/{species_id}/ecology-data")
async def get_species_ecology_data(
    species_id: str,
    common_name: str = Query(...),
    scientific_name: str = Query(...)
):
    """
    Get or generate 10 specific ecological answers for a species.
    Uses Supabase as a cache-layer before hitting Gemini.
    """
    supabase = get_supabase()

    # Check cache
    cached_data = []
    try:
        result = supabase.table("species_cached_answers").select(
            "*").eq("species_id", species_id).execute()
        cached_data = result.data or []
    except Exception as e:
        logger.error(f"Supabase select error (table missing or RLS?): {e}")

    EXPECTED_KEYS = [
        "taxonomic_identity", "geographic_distribution", "diet", "predators",
        "activity_patterns", "reproductive_traits", "migration", "habitat",
        "threats", "population_trends"
    ]

    if len(cached_data) >= 10:
        return {row["question_key"]: row["answer_text"] for row in cached_data}

    # Generate on cache miss
    try:
        answers = await generate_ecology_answers(common_name, scientific_name)
    except Exception as e:
        logger.warning(f"Ecology generation failed for {common_name}: {e}")
        answers = {}
    if not answers:
        answers = {
            key: "Information unavailable." for key in EXPECTED_KEYS
        }

    # Prepare rows for insert
    import uuid
    rows_to_insert = [
        {
            "id": str(uuid.uuid4()),
            "species_id": species_id,
            "question_key": key,
            "answer_text": answers.get(key, "Information unavailable.")
        }
        for key in EXPECTED_KEYS
    ]

    try:
        supabase.table("species_cached_answers").upsert(
            rows_to_insert, on_conflict="species_id,question_key").execute()
    except Exception as e:
        logger.error(f"Failed to cache ecology data: {e}")

    return {row["question_key"]: row["answer_text"] for row in rows_to_insert}
