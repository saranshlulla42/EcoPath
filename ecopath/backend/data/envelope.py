"""
The common shape every retrieval returns.

Before this layer, each source returned whatever its upstream happened to send:
GBIF dicts, eBird arrays, Movebank JSON, scraped HTML fragments. Nothing carried
where it came from or how old it was, so a wrong number in the UI could not be
traced back to a source, and the agent could not attribute its own figures.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Provenance:
    """Where a payload came from and how it was obtained."""

    source: str                      # registry id, e.g. "gbif"
    operation: str                   # e.g. "occurrence_counts"
    fetched_at: float                # unix seconds
    cached: bool = False             # served from cache rather than the network
    upstream_url: Optional[str] = None
    params: dict = field(default_factory=dict)
    degraded: bool = False           # a fallback path was used
    note: Optional[str] = None       # why it degraded, or any caveat

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "operation": self.operation,
            "fetched_at": self.fetched_at,
            "age_seconds": round(time.time() - self.fetched_at, 1),
            "cached": self.cached,
            "upstream_url": self.upstream_url,
            "degraded": self.degraded,
            "note": self.note,
        }


@dataclass
class Result(Generic[T]):
    """A payload plus its provenance. `ok` is false when every path failed."""

    data: T
    provenance: Provenance
    ok: bool = True
    error: Optional[str] = None

    @property
    def source(self) -> str:
        return self.provenance.source

    def as_dict(self) -> dict:
        return {
            "data": self.data,
            "ok": self.ok,
            "error": self.error,
            "provenance": self.provenance.as_dict(),
        }


def ok(data: Any, source: str, operation: str, **kw) -> Result:
    return Result(data=data, provenance=Provenance(
        source=source, operation=operation, fetched_at=time.time(), **kw
    ))


def failed(source: str, operation: str, error: str, data: Any = None, **kw) -> Result:
    return Result(
        data=data if data is not None else [],
        provenance=Provenance(
            source=source, operation=operation, fetched_at=time.time(),
            degraded=True, note=error, **kw
        ),
        ok=False,
        error=error,
    )
