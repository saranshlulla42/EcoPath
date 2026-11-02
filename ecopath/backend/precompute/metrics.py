"""Per-species migration metrics, computed from occurrence points.

Pure functions over plain data, so every number here is testable without a
database or a network. Nothing in this module classifies anything — it only
measures, and it reports how much it had to measure with.

The coverage fields exist because of the domain rule that "not migratory" and
"we don't know" are different answers. A metric like `max_displacement_km` is
meaningless on its own: 40 records from three months of the year produce a small
displacement whether the bird is a resident or a poorly-sampled migrant. Every
metric is therefore paired with the evidence behind it — record count, months
with data, spatial spread, sampling fraction — so the classifier can refuse to
answer rather than guess.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float
    month: Optional[int] = None
    year: Optional[int] = None
    state: Optional[str] = None


@dataclass
class MonthlyCentroid:
    month: int
    n_points: int
    lat: float
    lng: float
    lat_min: float
    lat_max: float
    spread_km: float


@dataclass
class SpeciesMetrics:
    total_records: int = 0
    points_with_month: int = 0
    months_with_data: int = 0
    max_displacement_km: Optional[float] = None
    displacement_months: Optional[str] = None
    lat_shift_deg: Optional[float] = None
    lat_range_deg: Optional[float] = None
    spatial_spread_km: Optional[float] = None
    effort_index: Optional[float] = None
    effort_basis: Optional[str] = None
    sampling_fraction: Optional[float] = None
    monthly: list[MonthlyCentroid] = field(default_factory=list)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def spherical_centroid(points: Sequence[Point]) -> tuple[float, float]:
    """
    Mean position on the sphere, not the arithmetic mean of coordinates.

    Averaging longitudes directly breaks across the antimeridian and distorts at
    high latitude. India never crosses the antimeridian, but this is cheap and
    stops the function being quietly wrong the first time it is used elsewhere.
    """
    if not points:
        raise ValueError("centroid of no points")
    x = y = z = 0.0
    for p in points:
        lat, lng = math.radians(p.lat), math.radians(p.lng)
        cos_lat = math.cos(lat)
        x += cos_lat * math.cos(lng)
        y += cos_lat * math.sin(lng)
        z += math.sin(lat)
    n = len(points)
    x, y, z = x / n, y / n, z / n
    hyp = math.hypot(x, y)
    if hyp < 1e-12 and abs(z) < 1e-12:
        # Antipodal scatter with no meaningful mean direction.
        return points[0].lat, points[0].lng
    return math.degrees(math.atan2(z, hyp)), math.degrees(math.atan2(y, x))


def mean_distance_km(points: Sequence[Point], lat: float, lng: float) -> float:
    """Mean great-circle distance of points from a position — a spread measure."""
    if not points:
        return 0.0
    return sum(haversine_km(p.lat, p.lng, lat, lng) for p in points) / len(points)


def monthly_centroids(points: Iterable[Point]) -> list[MonthlyCentroid]:
    """
    One centroid per month that has data.

    Months without points are absent rather than interpolated: a gap is
    information, and filling it would manufacture the very confidence the
    coverage fields exist to withhold.
    """
    buckets: dict[int, list[Point]] = {}
    for p in points:
        if p.month is None or not 1 <= p.month <= 12:
            continue
        buckets.setdefault(p.month, []).append(p)

    out: list[MonthlyCentroid] = []
    for month in sorted(buckets):
        group = buckets[month]
        lat, lng = spherical_centroid(group)
        lats = [p.lat for p in group]
        out.append(
            MonthlyCentroid(
                month=month,
                n_points=len(group),
                lat=lat,
                lng=lng,
                lat_min=min(lats),
                lat_max=max(lats),
                spread_km=mean_distance_km(group, lat, lng),
            )
        )
    return out


def max_centroid_displacement(
    centroids: Sequence[MonthlyCentroid],
) -> tuple[Optional[float], Optional[str]]:
    """
    Largest great-circle distance between any two monthly centroids, and the
    pair that produced it.

    All pairs, not just January-July: a species can be displaced between any two
    months, and assuming a northern-hemisphere summer/winter axis would hide
    exactly the monsoon-driven movement that matters in India.
    """
    if len(centroids) < 2:
        return None, None
    best = 0.0
    pair = None
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            a, b = centroids[i], centroids[j]
            d = haversine_km(a.lat, a.lng, b.lat, b.lng)
            if d > best:
                best, pair = d, f"{a.month}-{b.month}"
    return best, pair


def compute(
    points: Sequence[Point],
    *,
    total_records: Optional[int] = None,
    gbif_total: Optional[int] = None,
    effort_index: Optional[float] = None,
    effort_basis: Optional[str] = None,
) -> SpeciesMetrics:
    """
    All metrics for one species.

    `total_records` defaults to the number of points supplied, but callers that
    know GBIF's own total should pass it: the honest denominator for coverage is
    what exists, not what was downloaded.
    """
    m = SpeciesMetrics(
        total_records=total_records if total_records is not None else len(points),
        points_with_month=sum(1 for p in points if p.month and 1 <= p.month <= 12),
        effort_index=effort_index,
        effort_basis=effort_basis,
    )
    if gbif_total:
        m.sampling_fraction = min(1.0, len(points) / gbif_total)

    if not points:
        return m

    annual_lat, annual_lng = spherical_centroid(points)
    m.spatial_spread_km = mean_distance_km(points, annual_lat, annual_lng)
    lats = [p.lat for p in points]
    m.lat_range_deg = max(lats) - min(lats)

    m.monthly = monthly_centroids(points)
    m.months_with_data = len(m.monthly)
    if m.monthly:
        centroid_lats = [c.lat for c in m.monthly]
        m.lat_shift_deg = max(centroid_lats) - min(centroid_lats)
    m.max_displacement_km, m.displacement_months = max_centroid_displacement(m.monthly)
    return m
