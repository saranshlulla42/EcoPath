"""
EcoPath — Anomalies Router
Detects, lists, and provides weather context for population anomalies.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from services.supabase_client import get_supabase
from services.weather_service import get_historical_weather
from services.gemini_service import stream_causal_reasoning

logger = logging.getLogger("ecopath.anomalies")
router = APIRouter()


@router.get("/{species_id}")
async def get_species_anomalies(
    species_id: UUID,
    severity: Optional[str] = Query(None, description="Filter by severity: low|medium|high|critical"),
    anomaly_type: Optional[str] = Query(None, description="Filter: surge|dip|local_extinction"),
):
    """
    Returns all detected anomalies for a species, ordered by severity then year.
    """
    supabase = get_supabase()

    query = (
        supabase.table("anomalies")
        .select("*")
        .eq("species_id", str(species_id))
    )

    if severity:
        query = query.eq("severity", severity)
    if anomaly_type:
        query = query.eq("anomaly_type", anomaly_type)

    result = query.order("year", desc=True).execute()

    if not result.data:
        return {
            "species_id": str(species_id),
            "anomalies": [],
            "total": 0,
        }

    return {
        "species_id": str(species_id),
        "anomalies": result.data,
        "total": len(result.data),
    }


@router.post("/detect")
async def trigger_anomaly_detection(
    species_id: Optional[UUID] = Query(None, description="Run for specific species, or all if omitted"),
    start_year: int = Query(2020, ge=2015, le=2024),
):
    """
    Triggers the PostgreSQL anomaly detection function.
    Detects anomalies using >1.5 standard deviations from 5-year rolling averages.
    """
    supabase = get_supabase()

    result = supabase.rpc(
        "run_anomaly_detection",
        {"p_start_year": start_year},
    ).execute()

    detected = result.data or []

    # Filter by species if provided
    if species_id:
        detected = [d for d in detected if d.get("species_id") == str(species_id)]

    return {
        "status": "completed",
        "anomalies_detected": len(detected),
        "results": detected[:50],  # Return first 50
    }


@router.get("/{anomaly_id}/weather-context")
async def get_anomaly_weather_context(anomaly_id: UUID):
    """
    Fetch or compute weather context for a specific anomaly.
    This enriches the anomaly with Open-Meteo historical weather data.
    """
    supabase = get_supabase()

    # Get anomaly with species info
    result = (
        supabase.table("anomalies")
        .select("*, species(common_name, scientific_name, primary_range)")
        .eq("id", str(anomaly_id))
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    anomaly = result.data

    # If weather_context already cached, return it
    if anomaly.get("weather_context"):
        return {
            "anomaly_id": str(anomaly_id),
            "weather_context": anomaly["weather_context"],
            "cached": True,
        }

    # Compute species centroid from population records for the anomaly year
    centroid_lat, centroid_lng = 22.0, 78.5  # fallback: India center
    try:
        species_id_str = anomaly.get("species_id")
        if species_id_str:
            centroid_result = supabase.rpc(
                "get_heatmap_geojson",
                {"p_species_id": species_id_str, "p_year": anomaly["year"]},
            ).execute()
            if centroid_result.data:
                features = centroid_result.data.get("features", [])
                if features:
                    lats = [f["geometry"]["coordinates"][1] for f in features if f.get("geometry")]
                    lngs = [f["geometry"]["coordinates"][0] for f in features if f.get("geometry")]
                    if lats and lngs:
                        centroid_lat = sum(lats) / len(lats)
                        centroid_lng = sum(lngs) / len(lngs)
    except Exception as e:
        logger.warning(f"Could not compute centroid: {e}")

    weather = await get_historical_weather(lat=centroid_lat, lng=centroid_lng, year=anomaly["year"])

    if weather:
        # Cache in DB
        supabase.table("anomalies").update(
            {"weather_context": weather}
        ).eq("id", str(anomaly_id)).execute()

    return {
        "anomaly_id": str(anomaly_id),
        "weather_context": weather,
        "cached": False,
    }
