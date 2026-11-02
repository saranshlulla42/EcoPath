"""
Every external data source EcoPath talks to, declared in one place.

Timeouts, retries, rate limits and cache lifetimes used to be inline constants
scattered across 17 call sites — eight different timeouts, retry on only two of
them, and no rate limiting anywhere except an ad-hoc sleep in the ingestor. A
source's policy now lives with its declaration, so it can be tuned, inspected
and reported on without hunting through call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config import get_settings

settings = get_settings()

HOUR = 3600
DAY = 24 * HOUR


@dataclass(frozen=True)
class SourceSpec:
    id: str
    label: str                       # human name, shown in provenance and the UI
    base_url: str
    timeout: float = 20.0
    max_attempts: int = 3
    # Concurrent in-flight requests allowed against this host. GBIF starts
    # returning 429 well before double digits; local Ollama must stay at 1.
    concurrency: int = 5
    default_ttl: float = HOUR        # cache lifetime for this source's reads
    requires_key: bool = False
    key: Optional[str] = None
    headers: dict = field(default_factory=dict)
    notes: str = ""

    @property
    def available(self) -> bool:
        """False when a source needs a key that is not configured."""
        return bool(self.key) if self.requires_key else True


def _spec(**kw) -> SourceSpec:
    return SourceSpec(**kw)


SOURCES: dict[str, SourceSpec] = {
    "gbif": _spec(
        id="gbif", label="GBIF", base_url=settings.gbif_base_url,
        timeout=30.0, concurrency=5, default_ttl=6 * HOUR,
        headers={"User-Agent": "EcoPath/1.0 (ecological research dashboard)"},
        notes="Occurrence records, taxonomy, media. No key required.",
    ),
    "ebird": _spec(
        id="ebird", label="eBird", base_url="https://api.ebird.org/v2",
        timeout=15.0, concurrency=4, default_ttl=30 * 60,
        requires_key=True, key=getattr(settings, "ebird_api_key", "") or None,
        notes="Recent and seasonal observations. Key must stay server-side.",
    ),
    "movebank": _spec(
        id="movebank", label="Movebank",
        base_url="https://www.movebank.org/movebank/service/public/json",
        timeout=30.0, concurrency=2, default_ttl=DAY,
        notes="Telemetry tracks. Blocks browser-origin requests, so must be proxied.",
    ),
    "xenocanto": _spec(
        id="xenocanto", label="xeno-canto", base_url=settings.xenocanto_base_url,
        timeout=15.0, concurrency=3, default_ttl=DAY,
        requires_key=True, key=settings.xenocanto_api_key or None,
        notes="Bird call recordings (API v3).",
    ),
    "openmeteo": _spec(
        id="openmeteo", label="Open-Meteo", base_url=settings.openmeteo_base_url,
        timeout=30.0, concurrency=6, default_ttl=7 * DAY,
        notes="Historical weather archive. Past years never change — cache hard.",
    ),
    "gdelt": _spec(
        id="gdelt", label="GDELT", base_url=settings.gdelt_base_url,
        timeout=10.0, concurrency=2, default_ttl=6 * HOUR,
        notes="News event index used as extinction-risk evidence.",
    ),
    "news": _spec(
        id="news", label="Google News RSS",
        base_url="https://news.google.com/rss/search",
        timeout=20.0, concurrency=2, default_ttl=6 * HOUR,
        notes="Fallback evidence feed when GDELT is thin.",
    ),
    "iucn": _spec(
        id="iucn", label="IUCN Red List", base_url=settings.iucn_base_url,
        timeout=20.0, concurrency=2, default_ttl=7 * DAY,
        requires_key=True, key=settings.iucn_api_token or None,
        notes="Official status API. Falls back to a scrape when unkeyed.",
    ),
    "iucn_public": _spec(
        id="iucn_public", label="IUCN Red List (public)",
        base_url="https://r.jina.ai/http://https://www.iucnredlist.org",
        timeout=20.0, concurrency=1, default_ttl=7 * DAY,
        headers={"User-Agent": "Mozilla/5.0"},
        notes="Scrape fallback for IUCN status when no API token is set.",
    ),
    "wikipedia": _spec(
        id="wikipedia", label="Wikipedia",
        base_url="https://en.wikipedia.org/api/rest_v1",
        timeout=12.0, concurrency=4, default_ttl=7 * DAY,
        headers={"User-Agent": "EcoPath/1.0 (https://github.com/ecopath-capstone)"},
        notes="Species summary text.",
    ),
    "wikidata": _spec(
        id="wikidata", label="Wikidata", base_url="https://query.wikidata.org",
        timeout=15.0, concurrency=2, default_ttl=7 * DAY,
        headers={"User-Agent": "EcoPath-Student-Project/1.0"},
        notes="SPARQL lookup for IUCN status when other paths fail.",
    ),
    "ollama": _spec(
        id="ollama", label="Ollama (local)", base_url=settings.ollama_base_url,
        timeout=float(settings.ollama_timeout_seconds), max_attempts=1,
        concurrency=1, default_ttl=0,
        notes="Local report model. Single-flight: concurrent calls thrash the GPU.",
    ),
}


def get_source(source_id: str) -> SourceSpec:
    try:
        return SOURCES[source_id]
    except KeyError:
        raise KeyError(
            f"Unknown data source {source_id!r}. Known: {', '.join(sorted(SOURCES))}"
        ) from None


def availability() -> dict[str, dict]:
    """Which sources are usable right now — surfaced by the health endpoint."""
    return {
        s.id: {
            "label": s.label,
            "available": s.available,
            "requires_key": s.requires_key,
            "reason": None if s.available else "API key not configured",
            "notes": s.notes,
        }
        for s in SOURCES.values()
    }
