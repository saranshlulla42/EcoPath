"""H3 aggregation of occurrence points, per species per month.

The migration map currently asks GBIF for points at request time. Precomputing
hex counts removes that dependency and, incidentally, removes a per-user rate
limit from the render path.

What these cells hold is a count of *observations*, not of birds. Occurrence
density is largely a map of where observers go, so nothing here may be presented
as abundance — the field is `n_points` and callers are expected to label it
observation density unless they have effort-corrected it themselves.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Sequence

import h3

from precompute.metrics import Point, spherical_centroid

# Resolution is a rendering choice, not a domain threshold, but it is still a
# magic number: res 4 cells average ~1,770 km2 (~26 km edge), which is roughly
# district-scale for India and keeps a country-wide view to a few thousand
# cells. Overridable per call so a zoomed view can request finer.
DEFAULT_RESOLUTION = 4


@dataclass(frozen=True)
class HexCell:
    month: int
    h3_index: str
    resolution: int
    n_points: int
    centroid_lat: float
    centroid_lng: float


def aggregate(
    points: Iterable[Point],
    resolution: int = DEFAULT_RESOLUTION,
) -> list[HexCell]:
    """
    Group points into H3 cells by month.

    Points with no month are skipped rather than pooled into a thirteenth
    bucket: the map is a month slider, and a cell that appears in no month is
    less misleading than one that appears in all of them.
    """
    buckets: dict[tuple[int, str], list[Point]] = defaultdict(list)
    for p in points:
        if p.month is None or not 1 <= p.month <= 12:
            continue
        cell = h3.latlng_to_cell(p.lat, p.lng, resolution)
        buckets[(p.month, cell)].append(p)

    out: list[HexCell] = []
    for (month, cell), group in buckets.items():
        lat, lng = spherical_centroid(group)
        out.append(
            HexCell(
                month=month,
                h3_index=cell,
                resolution=resolution,
                n_points=len(group),
                centroid_lat=lat,
                centroid_lng=lng,
            )
        )
    out.sort(key=lambda c: (c.month, -c.n_points, c.h3_index))
    return out


def cell_boundary(h3_index: str) -> list[tuple[float, float]]:
    """Polygon ring for a cell, as (lat, lng) pairs, for map rendering."""
    return [(lat, lng) for lat, lng in h3.cell_to_boundary(h3_index)]


def to_geojson(cells: Sequence[HexCell]) -> dict:
    """
    FeatureCollection of hex polygons.

    `n_points` is carried through unchanged and named for what it is; any
    intensity scaling is the caller's decision, made where the legend lives.
    """
    features = []
    for c in cells:
        ring = [[lng, lat] for lat, lng in cell_boundary(c.h3_index)]
        if ring and ring[0] != ring[-1]:
            ring.append(ring[0])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {
                    "h3_index": c.h3_index,
                    "month": c.month,
                    "n_points": c.n_points,
                    "resolution": c.resolution,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}
