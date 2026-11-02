"""
A cached, human-readable summary of what EcoPath's database actually holds.

The agent used to have no way of knowing its own coverage, so an empty query
result was indistinguishable from an ecological finding — it would answer
"no observation records" and then invent reasons a species might be missing.
Injecting real coverage figures into every system prompt makes the difference
between "we have no data" and "the data says none" checkable by the model.

The summary is refreshed on a TTL rather than per turn: it changes only when
ingestion runs, and a stale number is far cheaper than a database round-trip
on the hot path of every message.
"""

import logging
import time
from typing import Optional

from services.supabase_client import get_supabase

logger = logging.getLogger("ecopath.agent.coverage")

COVERAGE_TTL_SECONDS = 600

_cache: Optional[str] = None
_cache_at: float = 0.0


def _format(coverage: dict) -> str:
    species_total = coverage.get("species_total") or 0
    with_records = coverage.get("species_with_records") or 0
    year_min, year_max = coverage.get("year_min"), coverage.get("year_max")
    states = coverage.get("states") or []
    iucn = coverage.get("iucn_breakdown") or {}

    lines = ["ECOPATH DATA COVERAGE (live):"]
    lines.append(
        f"- Species catalogued: {species_total}; with observation records: {with_records}"
    )
    if year_min and year_max:
        lines.append(f"- Population records: {coverage.get('population_records', 0)} "
                     f"covering {year_min}-{year_max}")
    lines.append(f"- Regions with data: {len(states)} Indian states/UTs")
    if iucn:
        ordered = [f"{k}: {v}" for k, v in sorted(iucn.items()) if k != "unknown"]
        lines.append(f"- IUCN breakdown: {', '.join(ordered)}")
    lines.append(
        f"- Threatened species (VU/EN/CR) with data: {coverage.get('threatened_with_data', 0)}"
    )
    lines.append(f"- Anomalies detected: {coverage.get('anomalies', 0)}")
    lines.append(f"- Migration routes stored: {coverage.get('migration_routes', 0)}")

    gaps = []
    if not coverage.get("anomalies"):
        gaps.append("the anomalies table is empty (detection has not been run)")
    if not coverage.get("migration_routes"):
        gaps.append("no migration routes are stored")
    missing = species_total - with_records
    if missing > 0:
        gaps.append(f"{missing} catalogued species have no population records")
    if gaps:
        lines.append(f"- Known gaps: {'; '.join(gaps)}")

    lines.append("")
    lines.append(
        "Treat these numbers as ground truth about your own holdings. If a query returns "
        "nothing, the correct answer is that EcoPath does not hold that data — never a "
        "hypothesis about why the birds are absent."
    )
    return "\n".join(lines)


async def get_coverage_summary(force: bool = False) -> str:
    """Cached coverage text for the system prompt. Empty string if unavailable."""
    global _cache, _cache_at

    if not force and _cache is not None and (time.time() - _cache_at) < COVERAGE_TTL_SECONDS:
        return _cache

    try:
        data = get_supabase().rpc("dataset_coverage").execute().data
        if isinstance(data, list):
            data = data[0] if data else {}
        if not data:
            return _cache or ""
        _cache = _format(data)
        _cache_at = time.time()
    except Exception as e:
        # A missing RPC (migration 06 not yet applied) must not break chat.
        logger.warning(f"Coverage summary unavailable: {e}")
        return _cache or ""

    return _cache


def invalidate() -> None:
    """Drop the cache — call after an ingestion run."""
    global _cache, _cache_at
    _cache, _cache_at = None, 0.0
