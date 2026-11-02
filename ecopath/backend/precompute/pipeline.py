"""Derive metrics and H3 aggregations from harvested points.

Separate from the harvest so metrics can be recomputed — after a scoring change,
a new H3 resolution, or a change of mind about coverage — without going back to
GBIF. The points are the expensive part; everything downstream is cheap.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from precompute import hexes, store
from precompute.metrics import Point, SpeciesMetrics, compute

logger = logging.getLogger("ecopath.precompute.pipeline")


def load_points(conn, species_id: str) -> list[Point]:
    rows = conn.execute(
        "SELECT lat, lng, month, year, state FROM occurrence_points WHERE species_id = ?",
        [species_id],
    ).fetchall()
    return [Point(lat=r[0], lng=r[1], month=r[2], year=r[3], state=r[4]) for r in rows]


def effort_for(conn, species_id: str) -> tuple[Optional[float], Optional[str]]:
    """
    A coarse sampling-effort proxy.

    eBird checklist data would be the right basis — observations per checklist
    corrects for observer activity — but the eBird API exposes recent
    observations and hotspots, not the historical checklist volume this needs
    (that lives in the eBird Basic Dataset, which is a request-and-download
    product). So this returns the honest fallback: how many distinct H3 cells
    and months the records span, which measures how spread the *sampling* was
    rather than how much of it there was.

    Returned with an explicit basis string so nothing downstream can mistake it
    for a checklist-corrected figure.
    """
    row = conn.execute(
        """
        SELECT COUNT(DISTINCT month) AS months,
               COUNT(DISTINCT state) AS states,
               COUNT(*)              AS n
        FROM occurrence_points
        WHERE species_id = ? AND month IS NOT NULL
        """,
        [species_id],
    ).fetchone()
    if not row or not row[2]:
        return None, None
    months, states, n = row
    # Points per (month x state) cell actually sampled: high means the records
    # pile up in few places and times, low means they are spread thin.
    denominator = max(1, months * states)
    return round(n / denominator, 3), "points per sampled month-state cell (no eBird checklist data)"


def compute_species(
    conn,
    species_id: str,
    *,
    scientific_name: str = "",
    common_name: str = "",
    catalogue_migratory: Optional[bool] = None,
    resolution: int = hexes.DEFAULT_RESOLUTION,
    write: bool = True,
) -> SpeciesMetrics:
    """Metrics, monthly centroids and hex aggregations for one species."""
    points = load_points(conn, species_id)

    log = conn.execute(
        "SELECT points_fetched, gbif_total FROM harvest_log WHERE species_id = ?",
        [species_id],
    ).fetchone()
    gbif_total = log[1] if log else None

    effort_index, effort_basis = effort_for(conn, species_id)
    m = compute(
        points,
        total_records=len(points),
        gbif_total=gbif_total,
        effort_index=effort_index,
        effort_basis=effort_basis,
    )

    if not write:
        return m

    conn.execute("DELETE FROM monthly_centroids WHERE species_id = ?", [species_id])
    if m.monthly:
        conn.executemany(
            "INSERT INTO monthly_centroids VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (species_id, c.month, c.n_points, c.lat, c.lng, c.lat_min, c.lat_max, c.spread_km)
                for c in m.monthly
            ],
        )

    cells = hexes.aggregate(points, resolution=resolution)
    conn.execute(
        "DELETE FROM species_month_hex WHERE species_id = ? AND resolution = ?",
        [species_id, resolution],
    )
    if cells:
        conn.executemany(
            "INSERT INTO species_month_hex VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (species_id, c.month, c.h3_index, c.resolution, c.n_points,
                 c.centroid_lat, c.centroid_lng)
                for c in cells
            ],
        )

    conn.execute("DELETE FROM species_metrics WHERE species_id = ?", [species_id])
    conn.execute(
        "INSERT INTO species_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            species_id,
            scientific_name,
            common_name,
            catalogue_migratory,
            m.total_records,
            m.points_with_month,
            m.months_with_data,
            m.max_displacement_km,
            m.displacement_months,
            m.lat_shift_deg,
            m.lat_range_deg,
            m.spatial_spread_km,
            m.effort_index,
            m.effort_basis,
            m.sampling_fraction,
            datetime.now(timezone.utc),
        ],
    )
    return m


def compute_all(
    conn,
    refs: Sequence,
    *,
    resolution: int = hexes.DEFAULT_RESOLUTION,
) -> int:
    """Recompute every harvested species. Cheap enough to run whenever."""
    n = 0
    for ref in refs:
        compute_species(
            conn,
            ref.species_id,
            scientific_name=ref.scientific_name,
            common_name=ref.common_name,
            catalogue_migratory=ref.migratory,
            resolution=resolution,
        )
        n += 1
    return n
