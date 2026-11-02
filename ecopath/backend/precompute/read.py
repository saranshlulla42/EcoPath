"""Read side of the precomputed store, for serving the migration map.

The map previously asked GBIF for occurrence points at request time, which put a
third-party rate limit on the render path and made every pan a network call.
These readers answer from the local DuckDB file instead.

What comes back is observation density, not abundance. `n_points` counts
records, which track where observers went as much as where birds were, so
callers must label it accordingly and must not present it as a population
figure.
"""

from __future__ import annotations

from typing import Optional

from precompute import hexes, store


def species_id_for(scientific_name: str) -> Optional[str]:
    """
    Map a scientific name to the internal species id.

    Scientific name is the join key between the Stage 3 taxonomy index (which
    keys on eBird species codes) and this store (which keys on the catalogue's
    UUIDs). It is exact on both sides, so no separate mapping table is needed —
    and matching on anything fuzzier would reintroduce the identity problem the
    resolver exists to remove.
    """
    conn = store.connect(read_only=True)
    try:
        row = conn.execute(
            "SELECT species_id FROM species_metrics WHERE lower(scientific_name) = lower(?)",
            [scientific_name.strip()],
        ).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def status_for(species_id: str) -> Optional[dict]:
    """The stored three-state verdict, with the evidence behind it."""
    conn = store.connect(read_only=True)
    try:
        row = conn.execute(
            """
            SELECT status, confidence, insufficient_basis, reasons, total_records,
                   months_with_data, max_displacement_km, sampling_fraction,
                   thresholds_used, classified_at
            FROM species_status WHERE species_id = ?
            """,
            [species_id],
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    keys = ["status", "confidence", "insufficient_basis", "reasons", "total_records",
            "months_with_data", "max_displacement_km", "sampling_fraction",
            "thresholds_used", "classified_at"]
    return dict(zip(keys, row))


def month_hexes(species_id: str, month: int, resolution: int | None = None) -> list[dict]:
    """Hex cells for one species in one month."""
    resolution = resolution if resolution is not None else hexes.DEFAULT_RESOLUTION
    conn = store.connect(read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT h3_index, n_points, centroid_lat, centroid_lng
            FROM species_month_hex
            WHERE species_id = ? AND month = ? AND resolution = ?
            ORDER BY n_points DESC
            """,
            [species_id, month, resolution],
        ).fetchall()
    finally:
        conn.close()
    return [
        {"h3_index": r[0], "n_points": r[1], "centroid_lat": r[2], "centroid_lng": r[3]}
        for r in rows
    ]


def month_hexes_geojson(species_id: str, month: int, resolution: int | None = None) -> dict:
    """The same cells as polygons, ready to render."""
    resolution = resolution if resolution is not None else hexes.DEFAULT_RESOLUTION
    cells = [
        hexes.HexCell(
            month=month,
            h3_index=c["h3_index"],
            resolution=resolution,
            n_points=c["n_points"],
            centroid_lat=c["centroid_lat"],
            centroid_lng=c["centroid_lng"],
        )
        for c in month_hexes(species_id, month, resolution)
    ]
    return hexes.to_geojson(cells)


def monthly_track(species_id: str) -> list[dict]:
    """
    The twelve monthly centroids, in order — the line a migration map draws.

    Months with no data are omitted rather than interpolated, so a gap in the
    track is visible as a gap.
    """
    conn = store.connect(read_only=True)
    try:
        rows = conn.execute(
            """
            SELECT month, n_points, centroid_lat, centroid_lng, spread_km
            FROM monthly_centroids WHERE species_id = ? ORDER BY month
            """,
            [species_id],
        ).fetchall()
    finally:
        conn.close()
    return [
        {"month": r[0], "n_points": r[1], "lat": r[2], "lng": r[3], "spread_km": r[4]}
        for r in rows
    ]


def species_metrics(species_id: str) -> Optional[dict]:
    """
    Stored metrics with their coverage.

    Returns None when the species was never harvested — which a caller must not
    render as "no movement". Not harvested and not moving are different facts.
    """
    conn = store.connect(read_only=True)
    try:
        row = conn.execute(
            """
            SELECT species_id, scientific_name, common_name, total_records,
                   months_with_data, max_displacement_km, displacement_months,
                   lat_shift_deg, lat_range_deg, spatial_spread_km,
                   effort_index, effort_basis, sampling_fraction, computed_at
            FROM species_metrics WHERE species_id = ?
            """,
            [species_id],
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    keys = [
        "species_id", "scientific_name", "common_name", "total_records",
        "months_with_data", "max_displacement_km", "displacement_months",
        "lat_shift_deg", "lat_range_deg", "spatial_spread_km",
        "effort_index", "effort_basis", "sampling_fraction", "computed_at",
    ]
    return dict(zip(keys, row))
