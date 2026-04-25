"""
EcoPath — Maps Router
Serves GeoJSON heatmap data and animated migration route data.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from services.supabase_client import get_supabase
from services.gbif_client import get_occurrence_points

logger = logging.getLogger("ecopath.maps")
router = APIRouter()


@router.get("/heatmap/{species_id}")
async def get_heatmap_data(
    species_id: UUID,
    year: int = Query(..., ge=2014, le=2024, description="Year for heatmap"),
    country: Optional[str] = Query(None, description="ISO 3166-1 alpha-2 country code (e.g. 'IN', 'US'). Omit for global data."),
):
    """
    Returns a GeoJSON FeatureCollection of observation points for heatmap rendering.
    Data is served from Supabase. Falls back to live GBIF fetch if DB is empty.
    Pass ?country=IN to filter by country, or omit for worldwide occurrences.
    """
    supabase = get_supabase()

    # Try DB first
    result = (
        supabase.rpc("get_heatmap_geojson", {
            "p_species_id": str(species_id),
            "p_year": year,
        })
        .execute()
    )

    geojson = result.data

    # If no DB data, fetch from GBIF live (will be slow but functional)
    if not geojson or geojson.get("features") == [] or not geojson:
        logger.info(f"No DB heatmap data for {species_id}/{year}, fetching from GBIF...")

        # Get species GBIF key from DB
        species_result = (
            supabase.table("species")
            .select("gbif_key, common_name")
            .eq("id", str(species_id))
            .single()
            .execute()
        )
        if not species_result.data:
            raise HTTPException(status_code=404, detail="Species not found")

        gbif_key = species_result.data["gbif_key"]
        points = await get_occurrence_points(gbif_key, year, limit=300, country_code=country)

        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
                "properties": {
                    "count": 1,
                    "state": p.get("state", "Unknown"),
                    "year": p.get("year", year),
                },
            }
            for p in points
        ]

        geojson = {
            "type": "FeatureCollection",
            "features": features,
        }

    feature_count = len(geojson.get("features", []))
    max_count = max(
        (f["properties"].get("count", 1) for f in geojson.get("features", [])),
        default=1,
    )

    return {
        "species_id": str(species_id),
        "year": year,
        "geojson": geojson,
        "total_points": feature_count,
        "max_count": max_count,
    }


@router.get("/heatmap/{species_id}/timeline")
async def get_heatmap_timeline(
    species_id: UUID,
    start_year: int = Query(2014),
    end_year: int = Query(2024),
):
    """
    Returns a dict of year → observation count for the temporal slider overlay.
    Used to visualize population change over time.
    """
    supabase = get_supabase()

    result = (
        supabase.rpc("get_yearly_totals", {"p_species_id": str(species_id)})
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="No population data found")

    timeline = {
        row["year"]: {
            "total": row["total_count"],
            "states": row["state_count"],
        }
        for row in result.data
        if start_year <= row["year"] <= end_year
    }

    # Fill missing years with 0
    for year in range(start_year, end_year + 1):
        if year not in timeline:
            timeline[year] = {"total": 0, "states": 0}

    return {
        "species_id": str(species_id),
        "timeline": timeline,
        "start_year": start_year,
        "end_year": end_year,
    }


@router.get("/migration/{species_id}")
async def get_migration_routes(species_id: UUID):
    """
    Returns all migration routes for a species as GeoJSON LineStrings
    with waypoint metadata for animation.
    """
    supabase = get_supabase()

    result = (
        supabase.table("migration_routes")
        .select("*")
        .eq("species_id", str(species_id))
        .execute()
    )

    if not result.data:
        return {
            "species_id": str(species_id),
            "routes": [],
            "message": "No migration data available for this species",
        }

    routes = []
    for route in result.data:
        waypoints = route.get("waypoints") or []
        if isinstance(waypoints, list) and waypoints:
            # Build LineString from waypoints for MapLibre animation
            coordinates = [[wp["lng"], wp["lat"]] for wp in waypoints]
            geojson = {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": {
                    "route_name": route["route_name"],
                    "flyway": route.get("flyway"),
                    "season": route.get("season"),
                    "direction": route.get("direction"),
                    "distance_km": route.get("distance_km"),
                    "active_months": route.get("active_months", []),
                    "waypoints": waypoints,
                },
            }
        else:
            geojson = None

        routes.append({
            "id": route["id"],
            "route_name": route["route_name"],
            "flyway": route.get("flyway"),
            "season": route.get("season"),
            "direction": route.get("direction"),
            "waypoints": waypoints,
            "active_months": route.get("active_months", []),
            "distance_km": route.get("distance_km"),
            "geojson": geojson,
        })

    return {
        "species_id": str(species_id),
        "routes": routes,
    }


@router.get("/india/bounds")
async def get_india_bounds():
    """Returns the center and zoom for India (kept for backwards compatibility)."""
    return {
        "center": [78.9629, 20.5937],
        "bounds": [[68.1766, 8.0706], [97.3954, 37.0902]],
        "zoom": 4.5,
    }
