import asyncio
import logging
import threading
from typing import Any, List, Optional

from data import repository as repo
from services.supabase_client import get_supabase

from collections import Counter

from agent import chart_store

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

# Spellings that appear in `population_records.state_name` but are not the
# canonical name. GBIF's GADM labels differ from ours ("NCT of Delhi"), and
# older ingests wrote free-text `stateProvince` values with typos. Filtering on
# the canonical name alone silently dropped every one of these rows.
STATE_ALIASES = {
    "maharastra": "Maharashtra",
    "andra pradesh": "Andhra Pradesh",
    "nct of delhi": "Delhi",
    "new delhi": "Delhi",
    "deli": "Delhi",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli",
    "orissa": "Odisha",
    "pondicherry": "Puducherry",
    "uttaranchal": "Uttarakhand",
}

STATE_TO_CODE = {v.lower(): k for k, v in STATE_CODES.items()}
STATE_TO_CODE.update({alias: STATE_TO_CODE[canon.lower()] for alias, canon in STATE_ALIASES.items()})


def canonical_state(name: Optional[str]) -> Optional[str]:
    """Fold a raw `state_name` value onto its canonical spelling."""
    if not name:
        return None
    return STATE_ALIASES.get(name.strip().lower(), name.strip())


def state_name_variants(region: str) -> List[str]:
    """
    Every spelling a region may be stored under, given a state code or a name.

    Used to build `IN (...)` filters so that a query for 'MH' also matches rows
    written as 'Maharastra'.
    """
    canon = CODE_TO_STATE.get(region.upper()) or canonical_state(region)
    if not canon:
        return [region]
    variants = {canon}
    for alias, target in STATE_ALIASES.items():
        if target == canon:
            variants.add(alias.title())
            variants.add(alias)
    # Preserve the exact stored casing for known GADM spellings.
    variants.update({"NCT of Delhi"} if canon == "Delhi" else set())
    variants.update({"Andaman and Nicobar"} if canon == "Andaman and Nicobar Islands" else set())
    return sorted(variants)

# Seasons as stored by `migration_routes.season` (02_schema.sql CHECK).
VALID_SEASONS = {"winter", "summer", "monsoon", "post-monsoon", "year-round"}

# Temperate season names the model reaches for, mapped onto the monsoon-based
# vocabulary the data actually uses. Anything unmapped means "no filter".
SEASON_ALIASES = {
    "autumn": "post-monsoon",
    "fall": "post-monsoon",
    "spring": "summer",
}

STATE_CENTROIDS = {
    "AP": (15.9129, 79.7400), "AR": (28.2180, 94.7278), "AS": (26.2006, 92.9376), "BR": (25.0961, 85.3131),
    "CG": (21.2787, 81.8661), "GA": (15.2993, 74.1240), "GJ": (22.2587, 71.1924), "HR": (29.0588, 76.0856),
    "HP": (31.1048, 77.1665), "JH": (23.6102, 85.2799), "KA": (15.3173, 75.7139), "KL": (10.8505, 76.2711),
    "MP": (22.9734, 78.6569), "MH": (19.7515, 75.7139), "MN": (24.6637, 93.9063), "ML": (25.4670, 91.3662),
    "MZ": (23.1645, 92.9376), "NL": (26.1584, 94.5624), "OD": (20.9517, 85.0985), "PB": (31.1471, 75.3412),
    "RJ": (27.0238, 74.2179), "SK": (27.5330, 88.5122), "TN": (11.1271, 78.6569), "TG": (18.1124, 79.0193),
    "TR": (23.9408, 91.9882), "UP": (26.8467, 80.9462), "UK": (30.0668, 79.0193), "WB": (22.9868, 87.8550),
}


def _species_ids_with_records(species_ids: set) -> set:
    """Kept as a thin alias; the implementation lives in the data layer."""
    return repo.species_ids_with_records(species_ids)


def _resolve_species(species_name: str) -> dict:
    """
    Resolve a species name through the unified data layer.

    This used to be a fourth, independent implementation of species matching,
    which meant the same name could resolve differently in chat than it did in
    the species browser or the extinction-risk report.
    """
    result = _run_sync(repo.resolve_species(species_name, allow_upstream=False))
    if not result.ok:
        return {"error": result.error or f"Could not resolve '{species_name}'"}

    data = result.data or {}
    if data.get("ambiguous"):
        return {
            "error": (
                f"'{species_name}' matches several species in EcoPath. "
                "Ask the user which one, or re-query with a full name."
            ),
            "candidates": data.get("candidates", []),
        }
    return data


def _run_sync(coro):
    """
    Bridge the async repository into the synchronous resolver.

    `_resolve_species` is called from sync code paths inside the tools; running
    the coroutine on a private loop in a worker thread keeps that contract
    without rewriting every caller.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict = {}

    def runner():
        result["value"] = asyncio.run(coro)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    return result["value"]


# ─── Payload budgets ─────────────────────────────────────────────────────────
# How much of a result the model actually sees. Full-fidelity series go to the
# chart store and are rendered by the frontend, so these govern context cost
# only — never what the user can be shown. Each is a one-line change.
SUMMARY_TOP_REGIONS = 5     # regions named individually in a summary
SUMMARY_TOP_SPECIES = 25    # species listed individually by list_species
SQL_MAX_ROWS_TO_MODEL = 50  # ad-hoc SQL rows the model sees, whatever it asked for


def _series_stats(points: List[dict], x: str = "year", y: str = "count") -> dict:
    """
    Reduce a year series to the handful of numbers an analyst would actually
    quote: endpoints, extremes, and the change between them.

    Returns coverage (`years_present`) alongside the values, because a two-point
    series and a ten-point series support very different claims and the model
    must be able to tell them apart.
    """
    if not points:
        return {"years_present": 0}
    vals = [(p[x], p[y] or 0) for p in points]
    first, last = vals[0], vals[-1]
    peak = max(vals, key=lambda v: v[1])
    trough = min(vals, key=lambda v: v[1])
    change = None
    if first[1]:
        change = round((last[1] - first[1]) / first[1] * 100, 1)
    return {
        "years_present": len(vals),
        "year_range": [vals[0][0], vals[-1][0]],
        "first": {"year": first[0], "value": first[1]},
        "last": {"year": last[0], "value": last[1]},
        "peak": {"year": peak[0], "value": peak[1]},
        "trough": {"year": trough[0], "value": trough[1]},
        "total": sum(v for _, v in vals),
        "change_pct_first_to_last": change,
    }


def _range_stats(vals: List[float]) -> Optional[dict]:
    """Min/mean/max for a weather variable — enough to describe conditions."""
    clean = [v for v in vals if v is not None]
    if not clean:
        return None
    return {
        "min": round(min(clean), 1),
        "mean": round(sum(clean) / len(clean), 1),
        "max": round(max(clean), 1),
        "n": len(clean),
    }


def _pearson(xs: List[float], ys: List[float]) -> Optional[dict]:
    """
    Pearson r for two equal-length series, with n reported alongside.

    Returns None rather than a number when there is too little overlap to mean
    anything — an r computed from two points is noise wearing a statistic's
    clothes.
    """
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    xs, ys = xs[:n], ys[:n]
    mx, my = sum(xs) / n, sum(ys) / n
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    num = sum(a * b for a, b in zip(dx, dy))
    den = (sum(a * a for a in dx) ** 0.5) * (sum(b * b for b in dy) ** 0.5)
    if not den:
        return None
    return {"r": round(num / den, 3), "n": n}


async def _population_frame(
    species_name: str,
    regions: Optional[List[str]] = None,
    year_start: int = 2014,
    year_end: int = 2024,
    max_regions: int = 10,
) -> dict:
    """
    Gather one species' observation series, before any summarisation.

    Kept separate from `query_population` so `compare_species` can work from the
    same full-fidelity frame: the tool-facing function reduces this to a summary
    the model sees, while the comparison needs the underlying points to build
    its own chart.

    Returns `{"error": ...}`, or `{"empty": True, "payload": ...}` when the
    species resolves but the slice holds nothing, or the populated frame.
    """
    try:
        species = _resolve_species(species_name)
        if "error" in species:
            return species

        supabase = get_supabase()
        query = supabase.table("population_records").select("*").eq("species_id", species["id"]).gte("year", year_start).lte("year", year_end)
        
        if regions and "IN" not in regions:
            state_names = []
            for r in regions:
                state_names.extend(state_name_variants(r))
            if state_names:
                query = query.in_("state_name", sorted(set(state_names)))
                
        result = query.execute()
        records = result.data or []
        
        if not records:
            # Distinguish "this species has no data at all" from "no data in
            # the requested slice" — the agent needs to say which, rather than
            # inventing an ecological reason for an ingestion gap.
            any_rows = (
                supabase.table("population_records")
                .select("year", count="exact")
                .eq("species_id", species["id"])
                .limit(1)
                .execute()
            )
            has_any = bool(any_rows.data)
            if has_any:
                note = (
                    "EcoPath holds records for this species, but none matching the requested "
                    "region and year filters. Widen the filters to see the data that exists."
                )
            else:
                note = (
                    "EcoPath holds no observation records for this species at all. State this "
                    "as a gap in EcoPath's dataset, not as an ecological finding, and do not "
                    "speculate about why the species is absent."
                )
            return {
                "empty": True,
                "species": species,
                "payload": {
                    "species": species.get("common_name", species_name),
                    "scientific_name": species.get("scientific_name"),
                    "conservation_status": species.get("iucn_status"),
                    "data": [],
                    "has_records_outside_filter": has_any,
                    "note": note,
                },
            }
            
        region_data = {}
        total_records = 0
        for r in records:
            state_name = canonical_state(r.get("state_name"))
            if not state_name or state_name in ("Pan-India", "Unknown"):
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
                "yearly_counts": counts_list,
            })

        # A wide-ranging species spans 25+ states; sending every one of them as a
        # full 10-year series is thousands of tokens the model does not need and,
        # on a rate-limited tier, cannot afford. Lead with the national series,
        # then the states that actually carry the signal.
        national: dict = {}
        for rd in final_data:
            for point in rd["yearly_counts"]:
                national[point["year"]] = national.get(point["year"], 0) + point["count"]

        final_data.sort(key=lambda rd: -sum(p["count"] for p in rd["yearly_counts"]))
        shown, omitted = final_data[:max_regions], final_data[max_regions:]

        national_points = [{"year": y, "count": c} for y, c in sorted(national.items())]
        return {
            "species": species,
            "shown": shown,
            "omitted": omitted,
            "national_points": national_points,
            "total_records": total_records,
            "regions_with_data": len(final_data),
        }

    except Exception as e:
        logger.error(f"query_population error: {e}")
        return {"error": f"Failed to fetch population data: {str(e)}"}


def _population_chart_series(frame: dict, top_n: int = SUMMARY_TOP_REGIONS) -> List[dict]:
    """National line first, then the regions carrying the most signal."""
    series = [
        {
            "name": "India (all regions)",
            "data": [{"x": str(p["year"]), "y": p["count"]} for p in frame["national_points"]],
        }
    ]
    for rd in frame["shown"][:top_n]:
        series.append(
            {
                "name": rd["region_name"],
                "data": [{"x": str(p["year"]), "y": p["count"]} for p in rd["yearly_counts"]],
            }
        )
    return series


async def query_population(
    species_name: str,
    regions: Optional[List[str]] = None,
    year_start: int = 2014,
    year_end: int = 2024,
    max_regions: int = 10,
) -> dict:
    frame = await _population_frame(species_name, regions, year_start, year_end, max_regions)
    if "error" in frame:
        return frame
    if frame.get("empty"):
        return frame["payload"]

    species = frame["species"]
    # The full series is registered for the frontend to draw. The model gets
    # numbers it can reason with and never sees the points, so bulk data crosses
    # the context window in neither direction.
    series_ref = chart_store.register_series(
        chart_type="line_chart",
        title=f"{species.get('common_name', species_name)} — observations by year",
        x_label="Year",
        y_label="Observations",
        series=_population_chart_series(frame),
    )

    return {
        "species": species.get("common_name", species_name),
        "scientific_name": species.get("scientific_name"),
        "conservation_status": species.get("iucn_status"),
        "requested_years": {"start": year_start, "end": year_end},
        # Observation counts, not abundance — uncorrected for survey effort.
        "national_observations": _series_stats(frame["national_points"]),
        "total_observations": frame["total_records"],
        "regions_with_data": frame["regions_with_data"],
        "top_regions": [
            {
                "region": rd["region"],
                "region_name": rd["region_name"],
                "observations": sum(p["count"] for p in rd["yearly_counts"]),
                "years_present": len(rd["yearly_counts"]),
            }
            for rd in frame["shown"][:SUMMARY_TOP_REGIONS]
        ],
        "series_ref": series_ref,
    }



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
        
        # Field names follow the `anomalies` table in 02_schema.sql. Earlier
        # versions read `actual_count`, `description` and `z_score`, none of
        # which exist, so every anomaly came back with null detail.
        wanted_variants = set(state_name_variants(region)) if region and region != "IN" else None

        formatted_anomalies = []
        for a in anomalies:
            state = canonical_state(a.get("affected_state"))
            formatted = {
                "year": a.get("year"),
                "type": a.get("anomaly_type"),
                "severity": a.get("severity"),
                "magnitude_pct": a.get("magnitude_pct"),
                "rolling_avg_5yr": a.get("rolling_avg_5yr"),
                "observed_count": a.get("observed_count"),
                "expected_count": a.get("expected_count"),
                "confidence_score": a.get("confidence_score"),
                "weather_context": a.get("weather_context"),
                "supporting_evidence": a.get("supporting_evidence"),
                "causal_hypothesis": a.get("causal_hypothesis"),
            }
            if state:
                formatted["region"] = STATE_TO_CODE.get(state.lower(), state)
                formatted["region_name"] = state

            if wanted_variants is not None:
                if not state or state not in {canonical_state(v) for v in wanted_variants}:
                    continue

            formatted_anomalies.append(formatted)
            
        # Sort by severity (critical first) then year desc
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        formatted_anomalies.sort(key=lambda x: (sev_order.get(x.get("severity", "low"), 4), -x.get("year", 0)))
        
        result_payload = {
            "species": species.get("common_name", species_name),
            "anomalies": formatted_anomalies,
            "total_anomalies": len(formatted_anomalies),
        }
        if not formatted_anomalies:
            total = supabase.table("anomalies").select("id", count="exact").limit(1).execute()
            if not total.data:
                result_payload["note"] = (
                    "EcoPath's anomaly table is empty — detection has not been run over the "
                    "current data. Report this as a pipeline gap, not as evidence that the "
                    "species is stable."
                )
            elif wanted_variants is not None and anomalies:
                # Detection runs on national yearly totals, so affected_state is
                # unset for most rows. Filtering by region then hides real
                # anomalies; say so rather than reporting "none found".
                result_payload["note"] = (
                    f"{len(anomalies)} anomalies exist for this species, but none carry a "
                    "state attribution, so the region filter excluded them. EcoPath detects "
                    "anomalies on national yearly totals; report them without a region."
                )
            else:
                result_payload["note"] = "No anomalies detected for this species under these filters."
        return result_payload
        
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

        # The stored vocabulary is winter|summer|monsoon|post-monsoon|year-round
        # (see the CHECK constraint in 02_schema.sql). The tool used to accept
        # spring|autumn, which matched nothing on every call.
        season_key = (season or "both").strip().lower()
        season_key = SEASON_ALIASES.get(season_key, season_key)
        filtered_by_season = season_key in VALID_SEASONS
        if filtered_by_season:
            query = query.eq("season", season_key)

        result = query.execute()
        routes = result.data or []

        # A season filter that matches nothing should not read as "this bird
        # has no routes". Fall back to the unfiltered set and say what happened.
        season_note = None
        if not routes and filtered_by_season:
            routes = (
                supabase.table("migration_routes")
                .select("*")
                .eq("species_id", species["id"])
                .execute()
            ).data or []
            if routes:
                stored = sorted({r.get("season") for r in routes if r.get("season")})
                season_note = (
                    f"No route is recorded for the '{season}' season; showing all "
                    f"{len(routes)} stored route(s) instead (recorded season(s): "
                    f"{', '.join(stored)})."
                )
        
        formatted_routes = []
        for r in routes:
            waypoints = r.get("waypoints") or []
            # Waypoints are seeded with `location_name`/`description` keys
            # (05_migration_seed.sql); reading `name`/`notes` returned a list
            # of anonymous "Stopover" entries with no detail.
            stopovers = [
                {
                    "name": wp.get("location_name") or wp.get("name") or "Stopover",
                    "lat": wp.get("lat"),
                    "lng": wp.get("lng"),
                    "month": wp.get("month"),
                    "notes": wp.get("description") or wp.get("notes") or "",
                }
                for wp in waypoints
                if "lat" in wp and "lng" in wp
            ]
            
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
            
        payload = {
            "species": species.get("common_name", species_name),
            "is_migratory": True,
            "routes": formatted_routes,
        }
        if season_note:
            payload["note"] = season_note
        elif not formatted_routes:
            payload["note"] = (
                f"{species.get('common_name', species_name)} is flagged as migratory but "
                "EcoPath stores no route geometry for it. Report this as a gap in the "
                "migration_routes table, not as evidence the species does not migrate."
            )
        return payload
        
    except Exception as e:
        logger.error(f"query_migration error: {e}")
        return {"error": f"Failed to fetch migration data: {str(e)}"}

async def compare_species(species_a: str, species_b: str, regions: Optional[List[str]] = None, year_start: int = 2014, year_end: int = 2024) -> dict:
    """Compare two species' observation series over the same window."""
    try:
        frame_a = await _population_frame(species_a, regions, year_start, year_end)
        if "error" in frame_a:
            return frame_a
        frame_b = await _population_frame(species_b, regions, year_start, year_end)
        if "error" in frame_b:
            return frame_b

        def side(frame: dict, requested: str) -> tuple[dict, list]:
            """One species' summary for the model, and its points for the chart."""
            sp = frame["species"]
            empty = frame.get("empty", False)
            points = [] if empty else frame["national_points"]
            summary = {
                "name": sp.get("common_name", requested),
                "scientific_name": sp.get("scientific_name"),
                "conservation_status": sp.get("iucn_status"),
                "habitat": ", ".join(sp.get("primary_habitat", []) or []),
                "diet": sp.get("diet", "Unknown"),
                # Absence of data and absence of birds are different findings;
                # the model must be able to tell them apart.
                "has_data": not empty,
                "regions_with_data": 0 if empty else frame["regions_with_data"],
                "observations": _series_stats(points),
            }
            return summary, points

        sum_a, pts_a = side(frame_a, species_a)
        sum_b, pts_b = side(frame_b, species_b)

        regions_a = set() if frame_a.get("empty") else {rd["region"] for rd in frame_a["shown"]}
        regions_b = set() if frame_b.get("empty") else {rd["region"] for rd in frame_b["shown"]}

        series_ref = chart_store.register_series(
            chart_type="line_chart",
            title=f"{sum_a['name']} vs {sum_b['name']} — observations by year",
            x_label="Year",
            y_label="Observations",
            series=[
                {"name": sum_a["name"], "data": [{"x": str(p["year"]), "y": p["count"]} for p in pts_a]},
                {"name": sum_b["name"], "data": [{"x": str(p["year"]), "y": p["count"]} for p in pts_b]},
            ],
        )

        return {
            "species_a": sum_a,
            "species_b": sum_b,
            "regions_in_common": sorted(regions_a & regions_b),
            "regions_only_a": sorted(regions_a - regions_b),
            "regions_only_b": sorted(regions_b - regions_a),
            "series_ref": series_ref,
        }
    except Exception as e:
        logger.error(f"compare_species error: {e}")
        return {"error": f"Failed to compare species data: {str(e)}"}


async def correlate_weather(species_name: str, region: str, year_start: int = 2014, year_end: int = 2024) -> dict:
    try:
        species = _resolve_species(species_name)
        if "error" in species:
            return species

        frame = await _population_frame(species_name, [region], year_start, year_end)
        if "error" in frame:
            return frame

        region_name = CODE_TO_STATE.get(region, region)
        centroid = STATE_CENTROIDS.get(region, (22.0, 78.5)) # Fallback to India center

        # The frame was gathered filtered to this one region, so its roll-up
        # across regions is precisely that region's yearly series.
        counts_by_year = {}
        if not frame.get("empty"):
            for point in frame["national_points"]:
                counts_by_year[point["year"]] = point["count"]
        
        yearly_data = []

        years = list(range(year_start, year_end + 1))
        weather = await repo.weather_years(centroid[0], centroid[1], years)
        by_year = weather.data or {}

        for year in years:
            w_res = by_year.get(year)
            if not w_res:
                continue
            
            yearly_data.append({
                "year": year,
                "observation_count": counts_by_year.get(year, 0),
                "avg_temp_c": w_res.get("annual_avg_temp_max"),
                "total_rainfall_mm": w_res.get("annual_precipitation_mm"),
                "monsoon_rainfall_mm": w_res.get("monsoon_precipitation_mm"),
                "extreme_heat_days": w_res.get("extreme_heat_days_gt40c")
            })
            
        def _col(key):
            return [(d["year"], d[key]) for d in yearly_data if d.get(key) is not None]

        obs = [{"year": y, "count": v} for y, v in _col("observation_count")]
        series_ref = chart_store.register_series(
            chart_type="line_chart",
            title=f"{species.get('common_name', species_name)} — observations in {region_name}",
            x_label="Year",
            y_label="Observations",
            series=[
                {
                    "name": species.get("common_name", species_name),
                    "data": [{"x": str(p["year"]), "y": p["count"]} for p in obs],
                }
            ],
        )

        # Without the raw points the model cannot eyeball a relationship, so the
        # coefficients are computed here instead. Reported with n so a
        # three-year overlap is not read like a ten-year one.
        correlations = {
            key: _pearson(
                [v for _, v in _col("observation_count")],
                [v for _, v in _col(key)],
            )
            for key in ("total_rainfall_mm", "monsoon_rainfall_mm", "avg_temp_c", "extreme_heat_days")
        }

        return {
            "species": species.get("common_name", species_name),
            "region": region,
            "region_name": region_name,
            "years_present": len(yearly_data),
            "observations": _series_stats(obs),
            # Range and mean only: the correlation coefficients below are what
            # the question actually turns on, and a full per-year stat block for
            # four weather variables costs more than it informs.
            "weather": {
                key: _range_stats([v for _, v in _col(key)])
                for key in ("total_rainfall_mm", "monsoon_rainfall_mm", "avg_temp_c", "extreme_heat_days")
            },
            "correlation_with_observations": correlations,
            "caveat": (
                "Correlations are over observation counts, which track recording effort as "
                "well as abundance. Treat them as suggestive, never causal, and always state n."
            ),
            "series_ref": series_ref,
        }
    except Exception as e:
        logger.error(f"correlate_weather error: {e}")
        return {"error": f"Failed to correlate weather: {str(e)}"}


# ═══════════════════════════════════════════════════════════════════════════
# Discovery, aggregation and open query
#
# The original five tools all required a named species, so any question of the
# form "which X has the most Y" was unanswerable. These four close that gap:
# `describe_dataset` grounds the agent in what exists, `list_species` and
# `rank_regions` cover catalogue-wide questions, and `run_sql` handles the
# long tail no typed tool anticipates.
# ═══════════════════════════════════════════════════════════════════════════

IUCN_LABELS = {
    "LC": "Least Concern", "NT": "Near Threatened", "VU": "Vulnerable",
    "EN": "Endangered", "CR": "Critically Endangered", "EW": "Extinct in the Wild",
    "EX": "Extinct", "DD": "Data Deficient", "NE": "Not Evaluated",
}
THREATENED = ("VU", "EN", "CR")

# Words users reach for that do not map onto a single IUCN code.
IUCN_GROUPS = {
    "threatened": list(THREATENED),
    "endangered": ["EN", "CR"],
    "at risk": list(THREATENED),
    "critically endangered": ["CR"],
    "vulnerable": ["VU"],
    "near threatened": ["NT"],
    "least concern": ["LC"],
}


def _normalize_iucn(value) -> Optional[List[str]]:
    """Turn a status word, code, or list into a list of IUCN codes."""
    if not value:
        return None
    values = [value] if isinstance(value, str) else list(value)
    codes: List[str] = []
    for v in values:
        key = str(v).strip().lower()
        if key in IUCN_GROUPS:
            codes.extend(IUCN_GROUPS[key])
        elif str(v).strip().upper() in IUCN_LABELS:
            codes.append(str(v).strip().upper())
    return sorted(set(codes)) or None


async def describe_dataset() -> dict:
    """
    What EcoPath actually holds: catalogue size, record coverage, year span,
    regions, and which tables are empty.
    """
    try:
        supabase = get_supabase()
        coverage = supabase.rpc("dataset_coverage").execute().data or {}
        if isinstance(coverage, list):
            coverage = coverage[0] if coverage else {}

        gaps = []
        if not coverage.get("anomalies"):
            gaps.append("The anomalies table is empty — anomaly detection has not been run.")
        if not coverage.get("migration_routes"):
            gaps.append("No migration routes are stored.")
        missing = (coverage.get("species_total") or 0) - (coverage.get("species_with_records") or 0)
        if missing > 0:
            gaps.append(
                f"{missing} of {coverage.get('species_total')} catalogued species have no "
                "population records."
            )

        return {
            "coverage": coverage,
            "known_gaps": gaps,
            "guidance": (
                "Use these figures when a query returns nothing. Say plainly that EcoPath "
                "lacks the data; never present a coverage gap as an ecological finding."
            ),
        }
    except Exception as e:
        logger.error(f"describe_dataset error: {e}")
        return {"error": f"Failed to read dataset coverage: {str(e)}"}


async def list_species(
    iucn_status: Optional[Any] = None,
    region: Optional[str] = None,
    migratory: Optional[bool] = None,
    family: Optional[str] = None,
    name_contains: Optional[str] = None,
    with_records_only: bool = False,
    limit: int = 50,
) -> dict:
    """
    Find species by conservation status, region, family or name — the
    discovery step that every 'which birds are...' question needs.
    """
    try:
        supabase = get_supabase()
        codes = _normalize_iucn(iucn_status)

        query = supabase.table("species").select(
            "id, common_name, scientific_name, family, order_name, iucn_status, "
            "migratory, endemic_india, primary_habitat"
        )
        if codes:
            query = query.in_("iucn_status", codes)
        if migratory is not None:
            query = query.eq("migratory", migratory)
        if family:
            query = query.ilike("family", f"%{family}%")
        if name_contains:
            query = query.or_(
                f"common_name.ilike.%{name_contains}%,scientific_name.ilike.%{name_contains}%"
            )

        rows = (query.limit(1000).execute()).data or []

        # Region and record-presence are properties of population_records, so
        # they are applied after the catalogue filter.
        ids_in_region = None
        if region and region.upper() != "IN":
            variants = state_name_variants(region)
            pop = (
                supabase.table("population_records")
                .select("species_id")
                .in_("state_name", variants)
                .limit(50000)
                .execute()
            ).data or []
            ids_in_region = {r["species_id"] for r in pop}
            rows = [r for r in rows if r["id"] in ids_in_region]

        if with_records_only and ids_in_region is None:
            with_data = _species_ids_with_records({r["id"] for r in rows})
            rows = [r for r in rows if r["id"] in with_data]

        rows.sort(key=lambda r: (r.get("iucn_status") or "ZZ", r["common_name"]))
        total = len(rows)

        # Counts come from the whole match set, so they stay true even though
        # only the head of the list is named individually below.
        by_iucn = Counter((r.get("iucn_status") or "unknown") for r in rows)
        by_family = Counter(r.get("family") or "unknown" for r in rows)
        migratory_count = sum(1 for r in rows if r.get("migratory"))
        endemic_count = sum(1 for r in rows if r.get("endemic_india"))

        shown = rows[: max(1, min(limit, SUMMARY_TOP_SPECIES))]

        payload = {
            "filters": {
                "iucn_status": codes,
                "region": region,
                "migratory": migratory,
                "family": family,
                "name_contains": name_contains,
                "with_records_only": with_records_only,
            },
            "total_matching": total,
            "counts_by_iucn": dict(by_iucn.most_common()),
            "top_families": [{"family": f, "species": n} for f, n in by_family.most_common(5)],
            "migratory_count": migratory_count,
            "endemic_india_count": endemic_count,
            "returned": len(shown),
            # `iucn_label` is dropped: it is a fixed lookup from `iucn_status`
            # that the model already knows, repeated on every row.
            "species": [
                {
                    "common_name": r["common_name"],
                    "scientific_name": r["scientific_name"],
                    "iucn_status": r.get("iucn_status"),
                }
                for r in shown
            ],
        }
        if total > len(shown):
            payload["note"] = (
                f"{total - len(shown)} further species match these filters and are counted in "
                "the totals above but not listed. Narrow the filters to name more of them."
            )
        return payload
    except Exception as e:
        logger.error(f"list_species error: {e}")
        return {"error": f"Failed to list species: {str(e)}"}


async def rank_regions(
    metric: str = "species_richness",
    iucn_status: Optional[Any] = None,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    limit: int = 15,
) -> dict:
    """
    Rank Indian states by a metric computed across the whole catalogue —
    species richness, total observations, or threatened-species count.
    """
    try:
        supabase = get_supabase()
        codes = _normalize_iucn(iucn_status)
        if metric == "threatened_species" and not codes:
            codes = list(THREATENED)

        rows = supabase.rpc(
            "rank_states",
            {
                "p_metric": "observations" if metric == "observations" else "species_richness",
                "p_iucn_statuses": codes,
                "p_year_start": year_start,
                "p_year_end": year_end,
                "p_limit": max(1, min(limit, 40)),
            },
        ).execute().data or []

        ranked = []
        for i, r in enumerate(rows, 1):
            state = canonical_state(r.get("state_name"))
            ranked.append({
                "rank": i,
                "region": STATE_TO_CODE.get((state or "").lower(), state),
                "region_name": state,
                "species_count": r.get("species_count"),
                "observation_total": r.get("observation_total"),
                "metric_value": r.get("metric_value"),
            })

        series_ref = chart_store.register_series(
            chart_type="bar_chart",
            title=f"States ranked by {metric.replace('_', ' ')}",
            x_label="State",
            y_label=metric.replace("_", " ").title(),
            series=[
                {
                    "name": metric.replace("_", " ").title(),
                    "data": [{"x": r["region_name"], "y": r["metric_value"] or 0} for r in ranked],
                }
            ],
        )

        return {
            "metric": metric,
            "iucn_filter": codes,
            "year_range": [year_start, year_end],
            "states_ranked": len(ranked),
            # Only the head of the ranking goes to the model; the frontend draws
            # the whole thing from the registered series.
            "top_regions": ranked[:SUMMARY_TOP_REGIONS],
            "series_ref": series_ref,
            "note": (
                "Counts reflect EcoPath's GBIF-derived holdings. Observation totals track "
                "recording effort as well as abundance, so treat them as relative, not absolute."
            ),
        }
    except Exception as e:
        logger.error(f"rank_regions error: {e}")
        return {"error": f"Failed to rank regions: {str(e)}"}


async def run_sql(query: str, row_limit: int = 200) -> dict:
    """
    Run a read-only SQL SELECT against the EcoPath tables.

    Executes server-side as a role with no write privileges, under a statement
    timeout and a hard row cap, so a malformed or hostile query can only fail —
    never mutate. This is the escape hatch for questions the typed tools do not
    cover.
    """
    try:
        supabase = get_supabase()
        rows = supabase.rpc(
            "exec_readonly_sql",
            {"p_query": query, "p_row_limit": max(1, min(row_limit, 2000))},
        ).execute().data

        if isinstance(rows, dict):
            rows = [rows]
        rows = rows or []
        # The database cap allows up to 2000 rows; the context window does not.
        # Cap again here, before serialisation, and say so explicitly so the
        # model reports a partial result rather than presenting it as complete.
        shown = rows[:SQL_MAX_ROWS_TO_MODEL]
        return {
            "query": query,
            "row_count": len(rows),
            "rows_shown": len(shown),
            "rows": shown,
            "truncated": len(rows) >= min(row_limit, 2000),
            "rows_withheld": max(len(rows) - len(shown), 0),
            "note": (
                f"Showing at most {SQL_MAX_ROWS_TO_MODEL} rows. Aggregate in SQL "
                "(COUNT, SUM, GROUP BY) rather than asking for raw rows."
            )
            if len(rows) > len(shown)
            else None,
        }
    except Exception as e:
        # Surface the database's own message: the model can usually repair its
        # SQL from "column X does not exist" and retry within the same turn.
        logger.warning(f"run_sql rejected query {query!r}: {e}")
        return {
            "query": query,
            "error": str(e),
            "hint": (
                "Only a single SELECT or WITH statement is allowed, over the tables "
                "species, population_records, anomalies and migration_routes."
            ),
        }
