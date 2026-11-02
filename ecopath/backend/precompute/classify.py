"""Three-state migration status.

`migratory`, `resident` and `insufficient_data` are three answers, not a boolean
with a caveat. The third is the default: a species starts as unknown and has to
earn a verdict by clearing coverage gates, because a tropical resident with 40
records and a poorly-sampled migrant produce the same small displacement and
nothing in the displacement number itself can tell them apart.

Thresholds are supplied, never defaulted. `Thresholds` has no default values and
`classify` raises without them — a plausible-looking constant baked in here
would silently become the project's answer to a question that belongs to the
person who knows the birds.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from precompute.metrics import SpeciesMetrics


class Status(str, Enum):
    MIGRATORY = "migratory"
    RESIDENT = "resident"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class Thresholds:
    """
    Cutoffs for the three-state decision. All required.

    `min_records`, `min_months_with_data` and `min_sampling_fraction` are the
    coverage gates: fail any and the answer is `insufficient_data` regardless of
    displacement.

    Displacement then uses two cutoffs, not one, because the validation set
    showed the groups genuinely overlap — known residents reach 473 km and known
    migrants drop to 343 km. A single boundary through that band would force a
    coin flip on real species. Above `migratory_above_km` is migratory, below
    `resident_below_km` is resident, and the band between is reported as
    insufficient_data with an explicit "inconclusive" basis.
    """

    migratory_above_km: float
    resident_below_km: float
    min_records: int
    min_months_with_data: int
    min_sampling_fraction: Optional[float] = None
    # A species seen across many months but only ever in one small area is
    # evidence of residency; one seen in a tiny area across two months is not
    # evidence of anything. Optional because it may not be wanted as a gate.
    min_spatial_spread_km: Optional[float] = None


@dataclass
class Classification:
    status: Status
    confidence: float
    reasons: list[str]
    # Why the answer is "we don't know": "coverage" (not enough data to judge)
    # or "inconclusive" (enough data, but the metric lands in the overlap band).
    # These read very differently to a user and must not be collapsed.
    insufficient_basis: Optional[str] = None
    # Echoed so a stored verdict always carries the evidence behind it, per the
    # rule that a classification may never travel without its coverage.
    total_records: int = 0
    months_with_data: int = 0
    max_displacement_km: Optional[float] = None
    sampling_fraction: Optional[float] = None
    thresholds_used: dict = None  # type: ignore[assignment]


def _coverage_score(m: SpeciesMetrics, t: Thresholds) -> float:
    """
    How much of the year, and how much of the record base, the verdict rests on.

    Each component saturates at the threshold: clearing a gate by a wide margin
    does not make the answer better, it just makes it not-worse.
    """
    parts: list[float] = []
    if t.min_months_with_data > 0:
        parts.append(min(1.0, m.months_with_data / max(t.min_months_with_data, 1)))
    if t.min_records > 0:
        parts.append(min(1.0, m.total_records / max(t.min_records, 1)))
    if t.min_sampling_fraction and m.sampling_fraction is not None:
        parts.append(min(1.0, m.sampling_fraction / t.min_sampling_fraction))
    return sum(parts) / len(parts) if parts else 0.0


def _decisiveness(displacement: float, cutoff: float) -> float:
    """
    How far the displacement sits from the cutoff, as 0..1.

    A species right at the boundary is a coin flip and should say so; one at ten
    times the cutoff is not in doubt. Scaled by the cutoff itself so it stays
    meaningful whatever value is chosen.
    """
    if cutoff <= 0:
        return 0.5
    return min(1.0, abs(displacement - cutoff) / cutoff)


def classify(m: SpeciesMetrics, t: Thresholds) -> Classification:
    reasons: list[str] = []

    def result(status: Status, confidence: float,
               basis: Optional[str] = None) -> Classification:
        return Classification(
            status=status,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
            reasons=reasons,
            insufficient_basis=basis,
            total_records=m.total_records,
            months_with_data=m.months_with_data,
            max_displacement_km=m.max_displacement_km,
            sampling_fraction=m.sampling_fraction,
            thresholds_used={
                "migratory_above_km": t.migratory_above_km,
                "resident_below_km": t.resident_below_km,
                "min_records": t.min_records,
                "min_months_with_data": t.min_months_with_data,
                "min_sampling_fraction": t.min_sampling_fraction,
                "min_spatial_spread_km": t.min_spatial_spread_km,
            },
        )

    # ── Coverage gates. Any failure ends in insufficient_data. ──────────────
    if m.total_records < t.min_records:
        reasons.append(f"only {m.total_records} records (need {t.min_records})")
    if m.months_with_data < t.min_months_with_data:
        reasons.append(
            f"data in {m.months_with_data} month(s) (need {t.min_months_with_data})"
        )
    if t.min_sampling_fraction is not None:
        if m.sampling_fraction is None:
            reasons.append("sampling fraction unknown")
        elif m.sampling_fraction < t.min_sampling_fraction:
            reasons.append(
                f"sampled {m.sampling_fraction:.1%} of known records "
                f"(need {t.min_sampling_fraction:.1%})"
            )
    if t.min_spatial_spread_km is not None and (
        m.spatial_spread_km is None or m.spatial_spread_km < t.min_spatial_spread_km
    ):
        reasons.append(
            f"points span {m.spatial_spread_km or 0:.0f} km "
            f"(need {t.min_spatial_spread_km:.0f} km)"
        )

    # Displacement needs at least two monthly centroids to exist at all.
    if m.max_displacement_km is None:
        reasons.append("fewer than two months with data, so no displacement to measure")

    if reasons:
        # Confidence here is confidence in the *verdict* — which is "we don't
        # know". It rises as coverage falls, because sparse data is strong
        # evidence that no claim should be made.
        return result(Status.INSUFFICIENT_DATA, 1.0 - _coverage_score(m, t) * 0.5,
                      basis="coverage")

    displacement = m.max_displacement_km or 0.0
    coverage = _coverage_score(m, t)

    if displacement >= t.migratory_above_km:
        reasons.append(
            f"monthly centroids move {displacement:.0f} km "
            f"(above {t.migratory_above_km:.0f} km) across months {m.displacement_months}"
        )
        decisiveness = _decisiveness(displacement, t.migratory_above_km)
        return result(Status.MIGRATORY, 0.5 + 0.5 * (0.6 * coverage + 0.4 * decisiveness))

    if displacement < t.resident_below_km:
        reasons.append(
            f"monthly centroids move only {displacement:.0f} km "
            f"(below {t.resident_below_km:.0f} km) despite {m.months_with_data} months of data"
        )
        decisiveness = _decisiveness(displacement, t.resident_below_km)
        return result(Status.RESIDENT, 0.5 + 0.5 * (0.6 * coverage + 0.4 * decisiveness))

    # The overlap band. There is plenty of data; it simply does not decide, and
    # saying so is more useful than a coin flip dressed as a verdict.
    reasons.append(
        f"monthly centroids move {displacement:.0f} km, between the resident "
        f"ceiling ({t.resident_below_km:.0f} km) and the migratory floor "
        f"({t.migratory_above_km:.0f} km) — the metric does not separate here"
    )
    return result(Status.INSUFFICIENT_DATA, 0.5, basis="inconclusive")
