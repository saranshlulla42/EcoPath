"""
The unified retrieval API.

Everything in EcoPath that needs data calls this module — routers, the chat
agent's tools, the extinction-risk service, the ingestor. It exposes domain
operations ("get me this species", "get me its occurrences") rather than source
operations, and decides internally which source answers: the local database
first where we hold the data, an upstream API where we do not.

That decision used to be duplicated and inconsistent. Species resolution alone
existed four times — in `agent/tools.py`, `routers/species.py`, the
extinction-risk service and the agent's state extractor — each with different
matching rules, so the same name could resolve differently depending on which
feature you entered through.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from data.envelope import Result, failed, ok
from data.sources import ebird, evidence, gbif, movebank, openmeteo, xenocanto
from services.supabase_client import get_supabase

logger = logging.getLogger("ecopath.data.repository")

# PostgREST caps an unbounded select at 1000 rows. The catalogue is larger than
# that, so full-table reads must page — otherwise they truncate silently, which
# is indistinguishable from the rows not existing.
PAGE_SIZE = 1000


def fetch_all(query_factory) -> list[dict]:
    """Read every row of a Supabase table through range pagination."""
    rows, offset = [], 0
    while True:
        page = query_factory().range(offset, offset + PAGE_SIZE - 1).execute().data or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


# ─── Species ─────────────────────────────────────────────────────────────────

async def resolve_species(name: str, allow_upstream: bool = True) -> Result:
    """
    Resolve a species name to a catalogue row.

    Local catalogue first: it carries curated fields (habitat, description,
    migratory flags) that GBIF does not. GBIF is consulted only for names we do
    not hold, and the result is marked degraded so callers know it is unbacked
    by local observation data.
    """
    needle = (name or "").strip()
    if not needle:
        return failed("supabase", "resolve_species", "Empty species name")

    try:
        rows = (
            get_supabase().table("species").select("*")
            .or_(f"common_name.ilike.%{needle}%,scientific_name.ilike.%{needle}%")
            .limit(200).execute()
        ).data or []
    except Exception as e:
        logger.error(f"species lookup failed: {e}")
        return failed("supabase", "resolve_species", str(e))

    if rows:
        lowered = needle.lower()
        exact = [r for r in rows
                 if r["common_name"].lower() == lowered
                 or r["scientific_name"].lower() == lowered]
        if exact:
            return ok(exact[0], "supabase", "resolve_species")
        if len(rows) == 1:
            return ok(rows[0], "supabase", "resolve_species")

        with_records = species_ids_with_records({r["id"] for r in rows})

        def is_prefix(r: dict) -> bool:
            return (r["common_name"].lower().startswith(lowered)
                    or r["scientific_name"].lower().startswith(lowered))

        def rank(r: dict) -> tuple:
            return (0 if r["id"] in with_records else 1, len(r["common_name"]))

        # Auto-resolve only on a genuine prefix match. Ranking a merely-contained
        # match by name length picks arbitrarily: "Gyps" would resolve to "Black
        # Vulture" — a New World vulture in a different genus — and present it
        # with full confidence. When nothing prefixes the query, say it is
        # ambiguous and let the caller choose.
        prefixed = sorted([r for r in rows if is_prefix(r)], key=rank)
        if len(prefixed) == 1:
            return ok(prefixed[0], "supabase", "resolve_species")
        if len(prefixed) > 1 and rank(prefixed[0]) < rank(prefixed[1]):
            return ok(prefixed[0], "supabase", "resolve_species")

        ranked = prefixed + sorted([r for r in rows if not is_prefix(r)], key=rank)
        return ok({
            "ambiguous": True,
            "candidates": [
                {"common_name": r["common_name"], "scientific_name": r["scientific_name"],
                 "iucn_status": r.get("iucn_status"), "has_records": r["id"] in with_records}
                for r in ranked[:10]
            ],
        }, "supabase", "resolve_species",
            note=f"{len(rows)} species match {needle!r}; ask which one")

    if not allow_upstream:
        return failed("supabase", "resolve_species",
                      f"'{needle}' is not in EcoPath's catalogue")

    match = await gbif.match_species_key(needle)
    if not match.ok or not match.data:
        return failed("gbif", "resolve_species",
                      f"'{needle}' is not in EcoPath's catalogue or GBIF")

    detail = await gbif.species_detail(match.data)
    if not detail.ok:
        return detail
    return ok(detail.data, "gbif", "resolve_species", degraded=True,
              note="Resolved from GBIF; EcoPath holds no local record for this species")


def species_ids_with_records(species_ids: set) -> set:
    if not species_ids:
        return set()
    try:
        rows = (get_supabase().table("population_records").select("species_id")
                .in_("species_id", list(species_ids)).limit(5000).execute()).data or []
        return {r["species_id"] for r in rows}
    except Exception as e:
        logger.warning(f"record-presence lookup failed: {e}")
        return set()


def species_catalogue(columns: str = "common_name,scientific_name") -> Result:
    """
    The whole catalogue, paged.

    The agent's entity extractor read this unpaginated and silently saw 1000 of
    1413 species, making 413 of them unrecognisable in chat.
    """
    try:
        rows = fetch_all(lambda: get_supabase().table("species").select(columns))
        return ok(rows, "supabase", "species_catalogue")
    except Exception as e:
        logger.error(f"catalogue read failed: {e}")
        return failed("supabase", "species_catalogue", str(e))


async def search_species(query: str, limit: int = 20) -> Result:
    """Catalogue search, topped up from GBIF when local results are thin."""
    try:
        rows = (get_supabase().table("species")
                .select("id, common_name, scientific_name, iucn_status, image_url, gbif_key")
                .or_(f"common_name.ilike.%{query}%,scientific_name.ilike.%{query}%")
                .limit(limit).execute()).data or []
    except Exception as e:
        return failed("supabase", "search_species", str(e))

    if len(rows) >= min(5, limit):
        return ok(rows, "supabase", "search_species")

    upstream = await gbif.search_species(query, limit=limit - len(rows))
    if not upstream.ok:
        return ok(rows, "supabase", "search_species", degraded=True,
                  note=f"GBIF supplement unavailable: {upstream.error}")

    known = {r.get("gbif_key") for r in rows}
    for item in (upstream.data or {}).get("results", []):
        key = item.get("key")
        if key in known:
            continue
        rows.append({
            "id": None, "gbif_key": key,
            "common_name": item.get("vernacularName") or item.get("canonicalName"),
            "scientific_name": item.get("canonicalName"),
            "iucn_status": None, "image_url": None, "from_gbif": True,
        })
    return ok(rows, "supabase", "search_species", degraded=True,
              note="Supplemented with GBIF results not held locally")


# ─── Observations ────────────────────────────────────────────────────────────

async def occurrences(species: dict, year_start: int, year_end: int,
                      states: Optional[list[str]] = None) -> Result:
    """Local population records; GBIF live only when we hold none."""
    try:
        q = (get_supabase().table("population_records").select("*")
             .eq("species_id", species["id"]).gte("year", year_start).lte("year", year_end))
        if states:
            q = q.in_("state_name", states)
        rows = q.limit(20000).execute().data or []
    except Exception as e:
        return failed("supabase", "occurrences", str(e))

    if rows:
        return ok(rows, "supabase", "occurrences")

    key = species.get("gbif_key")
    if not key:
        return ok([], "supabase", "occurrences",
                  note="EcoPath holds no records for this species")

    live = await gbif.occurrence_counts_by_year(key, year_start, year_end)
    if not live.ok:
        return ok([], "supabase", "occurrences", degraded=True, note=live.error)
    return ok([
        {"species_id": species.get("id"), "year": p["year"],
         "observation_count": p["count"], "state_name": None, "data_source": "GBIF-live"}
        for p in live.data
    ], "gbif", "occurrences", degraded=True,
        note="Live GBIF totals; not stored locally and not state-resolved")


async def recent_sightings(species_code: str, back: int = 30) -> Result:
    return await ebird.recent_observations(species_code, back=back)


async def seasonal_sightings(species_code: str, year: int) -> Result:
    return await ebird.seasonal_observations(species_code, year)


async def heatmap_points(gbif_key: int, year: int, limit: int = 300) -> Result:
    return await gbif.occurrence_points(gbif_key, year, limit=limit)


# ─── Movement ────────────────────────────────────────────────────────────────

async def migration_routes(species_id: str) -> Result:
    try:
        rows = (get_supabase().table("migration_routes").select("*")
                .eq("species_id", species_id).execute()).data or []
        return ok(rows, "supabase", "migration_routes")
    except Exception as e:
        return failed("supabase", "migration_routes", str(e))


async def telemetry_studies(scientific_name: str) -> Result:
    return await movebank.studies(scientific_name)


async def telemetry_tracks(study_id: int) -> Result:
    return await movebank.tracks(study_id)


# ─── Media ───────────────────────────────────────────────────────────────────

async def bird_call(scientific_name: str, country: Optional[str] = "india") -> Result:
    return await xenocanto.bird_call(scientific_name, country=country)


async def bird_call_audio(recording_id: str) -> Result:
    return await xenocanto.audio_bytes(recording_id)


async def species_images(gbif_key: int, limit: int = 5) -> Result:
    return await gbif.species_media(gbif_key, limit=limit)


# ─── Environment ─────────────────────────────────────────────────────────────

async def weather(lat: float, lng: float, year: int) -> Result:
    return await openmeteo.historical_year(lat, lng, year)


async def weather_years(lat: float, lng: float, years: list[int]) -> Result:
    return await openmeteo.historical_years(lat, lng, years)


# ─── Evidence ────────────────────────────────────────────────────────────────

async def conservation_status(scientific_name: str) -> Result:
    """
    IUCN status, trying each route in descending authority.

    Keyed API, then the public site, then Wikidata. Whichever answers, the
    result says which — a Wikidata-derived status should not be presented with
    the same confidence as the official API.
    """
    for lookup in (evidence.iucn_status, evidence.wikidata_iucn):
        res = await lookup(scientific_name)
        if res.ok and (res.data or {}).get("category"):
            return res
    return ok({}, "iucn", "conservation_status", degraded=True,
              note=f"No IUCN status resolved for {scientific_name}")


async def news_evidence(query: str, max_records: int = 6,
                        country_code: Optional[str] = None) -> Result:
    """GDELT first, Google News as backfill when GDELT is thin or rate-limited."""
    primary = await evidence.gdelt(query, max_records)
    items = list(primary.data or [])
    if len(items) >= max_records:
        return ok(items, "gdelt", "news_evidence", cached=primary.provenance.cached)

    backfill = await evidence.news_rss(query, max_records - len(items), country_code)
    seen = {i["url"] for i in items}
    items.extend(i for i in (backfill.data or []) if i["url"] not in seen)
    return ok(items, "gdelt+news", "news_evidence", degraded=True,
              note="GDELT results were thin; supplemented with Google News RSS")


async def species_context(scientific_name: str, common_name: str = "") -> Result:
    return await evidence.wikipedia_summary(scientific_name, common_name)
