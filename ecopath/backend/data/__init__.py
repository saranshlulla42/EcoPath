"""
EcoPath's unified data layer.

One entry point for every data source — local Supabase tables and eleven
external APIs. Call `repository` for domain operations; reach into
`data.sources.*` only when you genuinely need one specific upstream.

    from data import repository

    result = await repository.resolve_species("White-rumped Vulture")
    if result.ok:
        print(result.data, result.provenance.source)
"""

from data import repository
from data.cache import cache
from data.envelope import Provenance, Result, failed, ok
from data.registry import SOURCES, availability, get_source

__all__ = [
    "repository", "cache", "Result", "Provenance", "ok", "failed",
    "SOURCES", "get_source", "availability",
]
