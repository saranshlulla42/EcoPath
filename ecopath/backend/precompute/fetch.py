"""Harvest georeferenced occurrence points from GBIF into the DuckDB store.

`population_records` was built from GBIF facet totals — exact yearly counts per
state, but no month and no coordinates. Everything this package computes needs
both, so the points have to be fetched separately.

The harvest is resumable and logged per species. That log is not bookkeeping: it
is what lets coverage distinguish "GBIF holds nothing for this bird" from "the
harvest stopped before reaching it", which are the same shape in the data and
very different answers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from data.sources import gbif
from precompute import store
from precompute.metrics import Point

logger = logging.getLogger("ecopath.precompute.fetch")

# GBIF returns at most 300 records per request and its search endpoint refuses
# offsets past 100,000, so this is a sample of large series, not a census. The
# sampling fraction is recorded per species so coverage can reflect that.
PAGE_SIZE = 300

# Concurrent species. GBIF is tolerant but not unlimited, and this runs against
# a shared public service.
DEFAULT_CONCURRENCY = 4


class SpeciesRef:
    """A species to harvest, resolved from the catalogue."""

    __slots__ = ("species_id", "gbif_key", "scientific_name", "common_name", "migratory")

    def __init__(
        self,
        species_id: str,
        gbif_key: Optional[int],
        scientific_name: str,
        common_name: str,
        migratory: Optional[bool] = None,
    ) -> None:
        self.species_id = species_id
        self.gbif_key = gbif_key
        self.scientific_name = scientific_name
        self.common_name = common_name
        self.migratory = migratory


async def fetch_species_points(
    ref: SpeciesRef,
    years: Sequence[int],
    per_month: int = PAGE_SIZE,
) -> tuple[list[Point], Optional[int], dict[int, int], Optional[str]]:
    """
    Points for one species, sampled evenly across the twelve calendar months.

    Sampling per month rather than per year is not a detail. GBIF returns
    records in a fixed order, so the first 300 of a year are almost all January:
    an early version of this harvest pulled 3,000 points for the Asian Koel and
    landed every one of them in month 1, which would have made every seasonal
    metric read as "no movement, one month of data" for every species.

    Returns (points, gbif_total, monthly_totals, error). Per-month failures are
    recorded rather than fatal, so a species with eleven good months is kept
    with its gap visible instead of discarded.
    """
    if not ref.gbif_key:
        return [], None, {}, "no gbif_key in catalogue"

    span = f"{years[0]},{years[-1]}"
    points: list[Point] = []
    errors: list[str] = []

    monthly_totals: dict[int, int] = {}
    try:
        facets = await gbif.occurrence_month_facets(ref.gbif_key, years[0], years[-1])
        if facets.ok and facets.data:
            monthly_totals = {int(k): int(v) for k, v in facets.data.items()}
    except Exception as e:
        errors.append(f"month facets: {type(e).__name__}")

    for month in range(1, 13):
        # Skip months GBIF says hold nothing: a request that can only return
        # zero rows is still a request against a shared public service.
        if monthly_totals and monthly_totals.get(month, 0) == 0:
            continue
        try:
            res = await gbif.occurrence_points(
                ref.gbif_key, span, limit=per_month, month=month
            )
        except Exception as e:
            errors.append(f"m{month}: {type(e).__name__}")
            continue
        if not res.ok:
            errors.append(f"m{month}: {res.error}")
            continue
        for p in res.data or []:
            points.append(
                Point(
                    lat=p["lat"],
                    lng=p["lng"],
                    # Trust the requested month over the payload: the filter is
                    # what defines the bucket.
                    month=p.get("month") or month,
                    year=p.get("year"),
                    state=p.get("state"),
                )
            )

    gbif_total = sum(monthly_totals.values()) if monthly_totals else None
    return points, gbif_total, monthly_totals, "; ".join(errors) if errors else None


async def harvest(
    refs: Iterable[SpeciesRef],
    years: Sequence[int],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    db_path=None,
    progress=None,
) -> dict:
    """Fetch and persist points for every species. Safe to re-run."""
    refs = list(refs)
    conn = store.connect(db_path)
    semaphore = asyncio.Semaphore(concurrency)
    stats = {"species": 0, "points": 0, "with_month": 0, "errors": 0, "skipped": 0}

    already = {
        row[0]
        for row in conn.execute(
            "SELECT species_id FROM harvest_log WHERE error IS NULL AND points_fetched > 0"
        ).fetchall()
    }

    async def one(ref: SpeciesRef) -> None:
        if ref.species_id in already:
            stats["skipped"] += 1
            return
        async with semaphore:
            points, gbif_total, monthly_totals, error = await fetch_species_points(ref, years)

        with_month = sum(1 for p in points if p.month)
        conn.execute("DELETE FROM occurrence_points WHERE species_id = ?", [ref.species_id])
        if points:
            conn.executemany(
                "INSERT INTO occurrence_points VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (ref.species_id, ref.gbif_key, p.year, p.month, p.lat, p.lng, p.state)
                    for p in points
                ],
            )
        conn.execute("DELETE FROM harvest_log WHERE species_id = ?", [ref.species_id])
        conn.execute(
            "INSERT INTO harvest_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ref.species_id,
                ref.gbif_key,
                ref.scientific_name,
                ref.common_name,
                f"{years[0]}-{years[-1]}",
                len(points),
                with_month,
                gbif_total,
                datetime.now(timezone.utc),
                error,
            ],
        )

        stats["species"] += 1
        stats["points"] += len(points)
        stats["with_month"] += with_month
        if error:
            stats["errors"] += 1
        if progress:
            progress(ref, len(points), with_month, error)

    await asyncio.gather(*(one(r) for r in refs))
    conn.close()
    return stats
