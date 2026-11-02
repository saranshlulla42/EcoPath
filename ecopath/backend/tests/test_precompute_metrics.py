"""Metrics and three-state classification.

The classification tests carry most of the weight, because the failure this
package exists to prevent is not an arithmetic error — it is confidently
answering "resident" for a bird nobody has looked at.
"""

import math

import pytest

from precompute.classify import Status, Thresholds, classify
from precompute.hexes import aggregate, to_geojson
from precompute.metrics import (
    Point,
    compute,
    haversine_km,
    max_centroid_displacement,
    monthly_centroids,
    spherical_centroid,
)


# ── geometry ────────────────────────────────────────────────────────────────

def test_haversine_matches_known_distance():
    # Delhi to Chennai, ~1,760 km.
    d = haversine_km(28.6139, 77.2090, 13.0827, 80.2707)
    assert 1700 < d < 1800


def test_haversine_is_symmetric_and_zero_on_identity():
    assert haversine_km(20.0, 75.0, 20.0, 75.0) == 0
    assert haversine_km(10, 20, 30, 40) == pytest.approx(haversine_km(30, 40, 10, 20))


def test_spherical_centroid_of_symmetric_points_is_the_middle():
    pts = [Point(lat=10, lng=70), Point(lat=20, lng=70)]
    lat, lng = spherical_centroid(pts)
    assert lat == pytest.approx(15, abs=0.1)
    assert lng == pytest.approx(70, abs=0.001)


def test_spherical_centroid_handles_antimeridian():
    # Arithmetic mean of the longitudes would give 0; the answer is 180.
    lat, lng = spherical_centroid([Point(lat=0, lng=179), Point(lat=0, lng=-179)])
    assert abs(abs(lng) - 180) < 0.001
    assert lat == pytest.approx(0, abs=0.001)


# ── monthly structure ───────────────────────────────────────────────────────

def test_months_without_data_are_absent_not_interpolated():
    pts = [Point(lat=10, lng=70, month=1), Point(lat=10, lng=70, month=7)]
    centroids = monthly_centroids(pts)
    assert [c.month for c in centroids] == [1, 7]


def test_points_without_a_month_are_excluded():
    pts = [Point(lat=10, lng=70, month=None), Point(lat=10, lng=70, month=3)]
    assert [c.month for c in monthly_centroids(pts)] == [3]


def test_displacement_finds_the_widest_pair_not_just_january_july():
    # The extremes sit in March and November; a Jan/Jul assumption misses them.
    pts = [
        Point(lat=8, lng=77, month=3),
        Point(lat=12, lng=77, month=7),
        Point(lat=30, lng=77, month=11),
    ]
    centroids = monthly_centroids(pts)
    dist, pair = max_centroid_displacement(centroids)
    assert pair == "3-11"
    assert dist == pytest.approx(haversine_km(8, 77, 30, 77), rel=0.01)


def test_displacement_is_none_with_fewer_than_two_months():
    assert max_centroid_displacement([]) == (None, None)
    single = monthly_centroids([Point(lat=1, lng=1, month=5)])
    assert max_centroid_displacement(single) == (None, None)


def test_compute_reports_coverage_alongside_the_metric():
    pts = [Point(lat=10 + i, lng=70, month=i + 1) for i in range(4)]
    m = compute(pts, gbif_total=400)
    assert m.months_with_data == 4
    assert m.total_records == 4
    assert m.sampling_fraction == pytest.approx(0.01)
    assert m.max_displacement_km > 0
    assert m.lat_shift_deg == pytest.approx(3, abs=0.01)


def test_compute_on_no_points_is_empty_not_an_error():
    m = compute([])
    assert m.total_records == 0
    assert m.months_with_data == 0
    assert m.max_displacement_km is None


# ── the three-state contract ────────────────────────────────────────────────

GATES = Thresholds(migratory_above_km=475, resident_below_km=350,
                   min_records=100, min_months_with_data=6)


def _spread(n_months: int, per_month: int, lat_span: float = 0.0):
    """Points across `n_months`, optionally drifting north by `lat_span` degrees."""
    pts = []
    for i in range(n_months):
        lat = 10 + (lat_span * i / max(n_months - 1, 1))
        pts.extend(Point(lat=lat, lng=77, month=i + 1) for _ in range(per_month))
    return pts


def test_insufficient_data_is_reachable_on_too_few_records():
    m = compute(_spread(n_months=8, per_month=2))  # 16 records, needs 100
    c = classify(m, GATES)
    assert c.status is Status.INSUFFICIENT_DATA
    assert any("records" in r for r in c.reasons)


def test_insufficient_data_is_reachable_on_too_few_months():
    m = compute(_spread(n_months=2, per_month=200))  # 400 records, 2 months
    c = classify(m, GATES)
    assert c.status is Status.INSUFFICIENT_DATA
    assert any("month" in r for r in c.reasons)


def test_insufficient_data_is_reachable_on_a_thin_sample():
    m = compute(_spread(n_months=12, per_month=20), gbif_total=1_000_000)
    t = Thresholds(migratory_above_km=475, resident_below_km=350,
                   min_records=100, min_months_with_data=6,
                   min_sampling_fraction=0.05)
    c = classify(m, t)
    assert c.status is Status.INSUFFICIENT_DATA
    assert any("sampled" in r for r in c.reasons)


def test_a_sparse_migrant_and_a_sparse_resident_both_say_unknown():
    """
    The exact confusion the third state exists for: two species with the same
    thin record base, one that moves and one that does not, must both come back
    as unknown rather than one being called resident.
    """
    sparse_resident = compute(_spread(n_months=3, per_month=5, lat_span=0))
    sparse_migrant = compute(_spread(n_months=3, per_month=5, lat_span=20))
    assert classify(sparse_resident, GATES).status is Status.INSUFFICIENT_DATA
    assert classify(sparse_migrant, GATES).status is Status.INSUFFICIENT_DATA


def test_the_overlap_band_reports_inconclusive_not_a_coin_flip():
    """
    Displacement between the two cutoffs is well-sampled but undecided. That is
    a different answer from "not enough data", and the basis says which.
    """
    m = compute(_spread(n_months=12, per_month=50, lat_span=3.7))  # ~410 km
    c = classify(m, GATES)
    assert c.status is Status.INSUFFICIENT_DATA
    assert c.insufficient_basis == "inconclusive"
    assert GATES.resident_below_km <= c.max_displacement_km < GATES.migratory_above_km


def test_coverage_failure_and_inconclusive_are_distinguishable():
    sparse = classify(compute(_spread(2, 5, 0)), GATES)
    banded = classify(compute(_spread(12, 50, 3.7)), GATES)
    assert sparse.status is banded.status is Status.INSUFFICIENT_DATA
    assert sparse.insufficient_basis == "coverage"
    assert banded.insufficient_basis == "inconclusive"


def test_well_sampled_mover_is_migratory():
    m = compute(_spread(n_months=12, per_month=50, lat_span=20))
    c = classify(m, GATES)
    assert c.status is Status.MIGRATORY
    assert c.max_displacement_km > GATES.migratory_above_km


def test_well_sampled_stayer_is_resident():
    m = compute(_spread(n_months=12, per_month=50, lat_span=0))
    c = classify(m, GATES)
    assert c.status is Status.RESIDENT


def test_every_classification_carries_its_evidence():
    """A verdict may never travel without the coverage behind it."""
    for m in (
        compute(_spread(12, 50, 20)),
        compute(_spread(12, 50, 0)),
        compute(_spread(2, 5, 0)),
    ):
        c = classify(m, GATES)
        assert c.total_records == m.total_records
        assert c.months_with_data == m.months_with_data
        assert c.thresholds_used["migratory_above_km"] == GATES.migratory_above_km
        assert c.reasons


def test_confidence_is_bounded_and_lower_near_the_cutoff():
    near = compute(_spread(12, 50, lat_span=4.31))   # ~478km, just over the line
    far = compute(_spread(12, 50, lat_span=20))      # far beyond it
    cn, cf = classify(near, GATES), classify(far, GATES)
    assert 0.0 <= cn.confidence <= 1.0
    assert 0.0 <= cf.confidence <= 1.0
    assert cf.confidence > cn.confidence


def test_thresholds_are_required():
    with pytest.raises(TypeError):
        Thresholds()  # type: ignore[call-arg]


# ── H3 ──────────────────────────────────────────────────────────────────────

def test_hex_aggregation_groups_by_month_and_cell():
    pts = [Point(lat=19.07, lng=72.87, month=1) for _ in range(5)]
    pts += [Point(lat=19.07, lng=72.87, month=2) for _ in range(3)]
    cells = aggregate(pts, resolution=4)
    assert {c.month for c in cells} == {1, 2}
    assert sum(c.n_points for c in cells) == 8
    assert len({c.h3_index for c in cells}) == 1  # same place, same cell


def test_hex_aggregation_skips_points_without_a_month():
    assert aggregate([Point(lat=19.07, lng=72.87, month=None)]) == []


def test_distant_points_land_in_different_cells():
    cells = aggregate(
        [Point(lat=19.07, lng=72.87, month=1), Point(lat=28.61, lng=77.20, month=1)],
        resolution=4,
    )
    assert len(cells) == 2


def test_geojson_rings_are_closed_polygons():
    cells = aggregate([Point(lat=19.07, lng=72.87, month=1)], resolution=4)
    gj = to_geojson(cells)
    assert gj["type"] == "FeatureCollection"
    ring = gj["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) >= 7  # hexagon plus the closing vertex
    assert gj["features"][0]["properties"]["n_points"] == 1
