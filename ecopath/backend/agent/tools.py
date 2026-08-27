import logging
from typing import Optional, List
from services.supabase_client import get_supabase
from services.weather_service import get_historical_weather

logger = logging.getLogger("ecopath.agent.tools")

STATE_CODES = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar",
    "CG": "Chhattisgarh", "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh",
    "JH": "Jharkhand", "KA": "Karnataka", "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra",
    "MN": "Manipur", "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha",
    "PB": "Punjab", "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu", "TG": "Telangana",
    "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand", "WB": "West Bengal",
    "AN": "Andaman and Nicobar Islands", "CH": "Chandigarh", "DN": "Dadra and Nagar Haveli",
    "DD": "Daman and Diu", "DL": "Delhi", "JK": "Jammu and Kashmir", "LA": "Ladakh",
    "LD": "Lakshadweep", "PY": "Puducherry"
}
CODE_TO_STATE = STATE_CODES
STATE_TO_CODE = {v.lower(): k for k, v in STATE_CODES.items()}

STATE_CENTROIDS = {
    "AP": (15.9129, 79.7400), "AR": (28.2180, 94.7278), "AS": (26.2006, 92.9376), "BR": (25.0961, 85.3131),
    "CG": (21.2787, 81.8661), "GA": (15.2993, 74.1240), "GJ": (22.2587, 71.1924), "HR": (29.0588, 76.0856),
    "HP": (31.1048, 77.1665), "JH": (23.6102, 85.2799), "KA": (15.3173, 75.7139), "KL": (10.8505, 76.2711),
    "MP": (22.9734, 78.6569), "MH": (19.7515, 75.7139), "MN": (24.6637, 93.9063), "ML": (25.4670, 91.3662),
    "MZ": (23.1645, 92.9376), "NL": (26.1584, 94.5624), "OD": (20.9517, 85.0985), "PB": (31.1471, 75.3412),
    "RJ": (27.0238, 74.2179), "SK": (27.5330, 88.5122), "TN": (11.1271, 78.6569), "TG": (18.1124, 79.0193),
    "TR": (23.9408, 91.9882), "UP": (26.8467, 80.9462), "UK": (30.0668, 79.0193), "WB": (22.9868, 87.8550),
}


def _resolve_species(species_name: str) -> dict:
    try:
        supabase = get_supabase()
        result = (
            supabase.table("species")
            .select("*")
            .or_(f"common_name.ilike.%{species_name}%,scientific_name.ilike.%{species_name}%")
            .execute()
        )
        if not result.data:
            return {"error": f"Species '{species_name}' not found in database"}
        
        # Exact match preferred
        exact_matches = [
            s for s in result.data 
            if s["common_name"].lower() == species_name.lower() or s["scientific_name"].lower() == species_name.lower()
        ]
        
        if len(exact_matches) == 1:
            return exact_matches[0]
        elif len(exact_matches) > 1:
            names = [s['common_name'] for s in exact_matches]
            return {"error": f"Multiple exact species match '{species_name}': {', '.join(names)}. Please be more specific."}
        elif len(result.data) > 1:
            names = [s['common_name'] for s in result.data]
            return {"error": f"Multiple species match '{species_name}': {', '.join(names)}. Please be more specific."}
        
        return result.data[0]
    except Exception as e:
        logger.error(f"Error resolving species: {e}")
        return {"error": f"Failed to fetch species data: {str(e)}"}

async def query_population(species_name: str, regions: Optional[List[str]] = None, year_start: int = 2014, year_end: int = 2024) -> dict:
    try:
        species = _resolve_species(species_name)
        if "error" in species:
            return species

        supabase = get_supabase()
        query = supabase.table("population_records").select("*").eq("species_id", species["id"]).gte("year", year_start).lte("year", year_end)
        
        if regions and "IN" not in regions:
            state_names = []
            for r in regions:
                if r in CODE_TO_STATE:
                    state_names.append(CODE_TO_STATE[r])
                else:
                    state_names.append(r) # In case they pass raw name
            if state_names:
                query = query.in_("state_name", state_names)
                
        result = query.execute()
        records = result.data or []
        
        if not records:
            return {
                "species": species.get("common_name", species_name),
                "scientific_name": species.get("scientific_name"),
                "conservation_status": species.get("iucn_status"),
                "data": [],
                "note": "No records exist for that region." if regions else "No records exist."
            }
            
        region_data = {}
        total_records = 0
        for r in records:
            state_name = r.get("state_name")
            if not state_name or state_name == "Pan-India":
                state_name = "India"
            state_code = STATE_TO_CODE.get(state_name.lower(), state_name)
            
            if state_code not in region_data:
                region_data[state_code] = {
                    "region": state_code,
                    "region_name": state_name,
                    "yearly_counts": {}
                }
                
            year = r["year"]
            count = r.get("observation_count") or 0
            region_data[state_code]["yearly_counts"][year] = region_data[state_code]["yearly_counts"].get(year, 0) + count
            total_records += count
            
        final_data = []
        for rd in region_data.values():
            counts_list = [{"year": k, "count": v} for k, v in sorted(rd["yearly_counts"].items())]
            final_data.append({
                "region": rd["region"],
                "region_name": rd["region_name"],
                "yearly_counts": counts_list
            })
            
        return {
            "species": species.get("common_name", species_name),
            "scientific_name": species.get("scientific_name"),
            "conservation_status": species.get("iucn_status"),
            "data": final_data,
            "total_records": total_records
        }
        
    except Exception as e:
        logger.error(f"query_population error: {e}")
        return {"error": f"Failed to fetch population data: {str(e)}"}

async def query_anomalies(species_name: str, region: Optional[str] = None, severity_min: str = "low", year: Optional[int] = None) -> dict:
    try:
        species = _resolve_species(species_name)
        if "error" in species:
            return species

        supabase = get_supabase()
        query = supabase.table("anomalies").select("*").eq("species_id", species["id"])
        if year:
            query = query.eq("year", year)
            
        # severity_min logic
        severities = ["low", "medium", "high", "critical"]
        if severity_min in severities:
            allowed_sevs = severities[severities.index(severity_min):]
            query = query.in_("severity", allowed_sevs)
            
        result = query.execute()
        anomalies = result.data or []
        
        # Map region filtering if region provided (anomalies table may not have region, we might need to filter manually or if it does, use it)
        # Assuming anomalies is regional or national. Wait, does anomalies table have region?
        # Let's filter in python if needed. 
        # Actually anomalies schema from routers/anomalies.py doesn't show region field but the spec says "region: 'GJ', 'region_name': 'Gujarat'".
        # If it's missing from DB, we'll just return what's in DB.
        
        formatted_anomalies = []
        for a in anomalies:
            formatted = {
                "year": a.get("year"),
                "type": a.get("anomaly_type"),
                "severity": a.get("severity"),
                "z_score": a.get("z_score"),
                "expected_count": a.get("expected_count"),
                "actual_count": a.get("actual_count"),
                "weather_context": a.get("weather_context"),
                "description": a.get("description")
            }
            region_val = a.get("region") or a.get("affected_state")
            if region_val:
                formatted["region"] = region_val
                formatted["region_name"] = CODE_TO_STATE.get(region_val, region_val)
            
            # If region filter provided and it doesn't match, skip
            if region and formatted.get("region") != region and region != "IN":
                continue
                
            formatted_anomalies.append(formatted)
            
        # Sort by severity (critical first) then year desc
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        formatted_anomalies.sort(key=lambda x: (sev_order.get(x.get("severity", "low"), 4), -x.get("year", 0)))
        
        return {
            "species": species.get("common_name", species_name),
            "anomalies": formatted_anomalies,
            "total_anomalies": len(formatted_anomalies)
        }
        
    except Exception as e:
        logger.error(f"query_anomalies error: {e}")
        return {"error": f"Failed to fetch anomaly data: {str(e)}"}

async def query_migration(species_name: str, season: str = "both") -> dict:
    try:
        species = _resolve_species(species_name)
        if "error" in species:
            return species

        if not species.get("migratory", False):
            return {
                "species": species.get("common_name", species_name),
                "is_migratory": False,
                "routes": [],
                "note": f"{species.get('common_name', species_name)} is a resident species and does not migrate."
            }

        supabase = get_supabase()
        query = supabase.table("migration_routes").select("*").eq("species_id", species["id"])
        
        if season in ["spring", "autumn"]:
            query = query.eq("season", season)
            
        result = query.execute()
        routes = result.data or []
        
        formatted_routes = []
        for r in routes:
            waypoints = r.get("waypoints") or []
            stopovers = [{"name": wp.get("name", "Stopover"), "lat": wp.get("lat"), "lng": wp.get("lng"), "notes": wp.get("notes", "")} for wp in waypoints if "lat" in wp and "lng" in wp]
            
            coordinates = [[wp.get("lng"), wp.get("lat")] for wp in waypoints if "lat" in wp and "lng" in wp]
            geojson = {
                "type": "LineString",
                "coordinates": coordinates
            } if coordinates else None
            
            formatted_routes.append({
                "route_name": r.get("route_name", "Unknown Route"),
                "season": r.get("season", "unknown"),
                "geojson": geojson,
                "stopovers": stopovers,
                "distance_km": r.get("distance_km"),
                "source": "Movebank telemetry + eBird observations"
            })
            
        return {
            "species": species.get("common_name", species_name),
            "is_migratory": True,
            "routes": formatted_routes
        }
        
    except Exception as e:
        logger.error(f"query_migration error: {e}")
        return {"error": f"Failed to fetch migration data: {str(e)}"}

async def compare_species(species_a: str, species_b: str, regions: Optional[List[str]] = None, year_start: int = 2014, year_end: int = 2024) -> dict:
    try:
        pop_a = await query_population(species_a, regions, year_start, year_end)
        if "error" in pop_a: return pop_a
        
        pop_b = await query_population(species_b, regions, year_start, year_end)
        if "error" in pop_b: return pop_b
        
        sp_a = _resolve_species(species_a)
        sp_b = _resolve_species(species_b)
        
        def agg_data(pop_data):
            yearly = {}
            for rd in pop_data.get("data", []):
                for y_data in rd.get("yearly_counts", []):
                    yearly[y_data["year"]] = yearly.get(y_data["year"], 0) + y_data["count"]
            return [{"year": k, "total_count": v} for k, v in sorted(yearly.items())]

        shared_regions = set()
        for rd in pop_a.get("data", []): shared_regions.add(rd["region"])
        for rd in pop_b.get("data", []): shared_regions.add(rd["region"])

        return {
            "species_a": {
                "name": sp_a.get("common_name", species_a),
                "scientific_name": sp_a.get("scientific_name"),
                "conservation_status": sp_a.get("iucn_status"),
                "habitat": ", ".join(sp_a.get("primary_habitat", [])),
                "diet": sp_a.get("diet", "Unknown"),
                "data": agg_data(pop_a)
            },
            "species_b": {
                "name": sp_b.get("common_name", species_b),
                "scientific_name": sp_b.get("scientific_name"),
                "conservation_status": sp_b.get("iucn_status"),
                "habitat": ", ".join(sp_b.get("primary_habitat", [])),
                "diet": sp_b.get("diet", "Unknown"),
                "data": agg_data(pop_b)
            },
            "shared_regions": list(shared_regions)
        }
    except Exception as e:
        logger.error(f"compare_species error: {e}")
        return {"error": f"Failed to compare species data: {str(e)}"}

async def correlate_weather(species_name: str, region: str, year_start: int = 2014, year_end: int = 2024) -> dict:
    try:
        species = _resolve_species(species_name)
        if "error" in species:
            return species

        pop = await query_population(species_name, regions=[region], year_start=year_start, year_end=year_end)
        if "error" in pop: return pop
        
        region_name = CODE_TO_STATE.get(region, region)
        centroid = STATE_CENTROIDS.get(region, (22.0, 78.5)) # Fallback to India center
        
        # Build year map for counts
        counts_by_year = {}
        for rd in pop.get("data", []):
            if rd["region"] == region or rd["region_name"] == region_name:
                for y_data in rd["yearly_counts"]:
                    counts_by_year[y_data["year"]] = counts_by_year.get(y_data["year"], 0) + y_data["count"]
        
        yearly_data = []
        import asyncio
        
        tasks = []
        for year in range(year_start, year_end + 1):
            tasks.append(get_historical_weather(lat=centroid[0], lng=centroid[1], year=year))
            
        weather_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for year, w_res in zip(range(year_start, year_end + 1), weather_results):
            if isinstance(w_res, Exception) or not w_res:
                continue
            
            yearly_data.append({
                "year": year,
                "observation_count": counts_by_year.get(year, 0),
                "avg_temp_c": w_res.get("annual_avg_temp_max"),
                "total_rainfall_mm": w_res.get("annual_precipitation_mm"),
                "monsoon_rainfall_mm": w_res.get("monsoon_precipitation_mm"),
                "extreme_heat_days": w_res.get("extreme_heat_days_gt40c")
            })
            
        return {
            "species": species.get("common_name", species_name),
            "region": region,
            "region_name": region_name,
            "yearly_data": yearly_data
        }
    except Exception as e:
        logger.error(f"correlate_weather error: {e}")
        return {"error": f"Failed to correlate weather: {str(e)}"}
