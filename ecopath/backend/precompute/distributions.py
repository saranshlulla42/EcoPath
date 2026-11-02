"""Summary statistics and histograms for threshold setting.

This module exists so the cutoffs are chosen from the data rather than guessed.
It renders the distribution of each candidate metric and, separately, a table of
species whose status is already known from the curated catalogue — so a proposed
cutoff can be checked against birds whose answer is not in doubt before it is
applied to the ~1,400 whose answer is.
"""

from __future__ import annotations

from typing import Optional, Sequence


def percentiles(values: Sequence[float], points=(0, 5, 10, 25, 50, 75, 90, 95, 100)) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    out = {}
    for p in points:
        idx = min(len(ordered) - 1, max(0, int(round(p / 100 * (len(ordered) - 1)))))
        out[f"p{p}"] = ordered[idx]
    return out


def histogram(
    values: Sequence[float],
    bins: Sequence[float],
    width: int = 34,
) -> list[str]:
    """Text histogram over explicit bin edges."""
    if not values:
        return ["  (no values)"]
    counts = [0] * (len(bins) + 1)
    for v in values:
        placed = False
        for i, edge in enumerate(bins):
            if v < edge:
                counts[i] += 1
                placed = True
                break
        if not placed:
            counts[-1] += 1

    peak = max(counts) or 1
    lines = []
    for i, c in enumerate(counts):
        if i == 0:
            label = f"< {bins[0]:g}"
        elif i == len(counts) - 1:
            label = f">= {bins[-1]:g}"
        else:
            label = f"{bins[i-1]:g}-{bins[i]:g}"
        bar = "#" * int(round(c / peak * width))
        lines.append(f"    {label:>14}  {c:>5}  {bar}")
    return lines


def metric_report(rows: Sequence[dict]) -> str:
    """
    Distributions of every candidate cutoff metric.

    Split by the curated `migratory` flag where it exists, because the useful
    question is not "what does the distribution look like" but "where do the two
    populations separate, and how much do they overlap".
    """
    out: list[str] = []
    add = out.append

    known_mig = [r for r in rows if r.get("known_status") == "migratory"]
    known_res = [r for r in rows if r.get("known_status") == "resident"]

    add("=" * 76)
    add(f"  {len(rows)} species with metrics "
        f"({len(known_mig)} known migratory, {len(known_res)} known resident, "
        f"{len(rows) - len(known_mig) - len(known_res)} unlabelled)")
    add("=" * 76)

    specs = [
        ("max_displacement_km", "Max displacement between monthly centroids (km)",
         [10, 25, 50, 100, 200, 400, 800, 1600]),
        ("lat_shift_deg", "Latitudinal shift of monthly centroids (deg)",
         [0.1, 0.25, 0.5, 1, 2, 4, 8]),
        ("spatial_spread_km", "Mean distance of points from annual centroid (km)",
         [50, 100, 200, 400, 800, 1600]),
        ("total_records", "Points harvested per species",
         [10, 25, 50, 100, 250, 500, 1000, 2000]),
        ("months_with_data", "Months of the year with any data",
         [1, 2, 3, 4, 6, 8, 10, 12]),
        ("sampling_fraction", "Harvested / GBIF total",
         [0.01, 0.05, 0.1, 0.25, 0.5, 0.9]),
    ]

    for key, title, bins in specs:
        values = [r[key] for r in rows if r.get(key) is not None]
        add("")
        add(f"  {title}")
        add(f"    n={len(values)} of {len(rows)}")
        if values:
            pct = percentiles(values)
            add("    " + "  ".join(f"{k}={v:,.4g}" for k, v in pct.items()))
        add("")
        out.extend(histogram(values, bins))

        if known_mig and known_res:
            mv = [r[key] for r in known_mig if r.get(key) is not None]
            rv = [r[key] for r in known_res if r.get(key) is not None]
            if mv and rv:
                add("")
                add(f"    known migratory : median {sorted(mv)[len(mv)//2]:,.4g}  "
                    f"(n={len(mv)}, min {min(mv):,.4g}, max {max(mv):,.4g})")
                add(f"    known resident  : median {sorted(rv)[len(rv)//2]:,.4g}  "
                    f"(n={len(rv)}, min {min(rv):,.4g}, max {max(rv):,.4g})")
    return "\n".join(out)


def known_species_table(rows: Sequence[dict], limit: Optional[int] = None) -> str:
    """
    Per-species figures for birds whose status is already known.

    This is the table to read a cutoff off: pick a displacement that puts the
    known migrants above it and the known residents below, then look at how many
    species fall in the overlap and would be better answered as unknown.
    """
    labelled = [r for r in rows if r.get("known_status")]
    labelled.sort(key=lambda r: (r.get("known_status") != "migratory",
                                 -(r.get("max_displacement_km") or 0)))
    if limit:
        labelled = labelled[:limit]

    lines = [
        "",
        "=" * 104,
        "  SPECIES WITH A KNOWN STATUS — read the cutoff off this table",
        "=" * 104,
        f"  {'species':<30}{'known':>10}{'displ_km':>10}{'lat_shift':>10}"
        f"{'spread_km':>11}{'months':>8}{'points':>8}{'sampled':>9}",
    ]
    for r in labelled:
        known = r["known_status"]
        frac = r.get("sampling_fraction")
        lines.append(
            f"  {(r.get('common_name') or '?')[:29]:<30}{known:>10}"
            f"{(r.get('max_displacement_km') or 0):>10,.0f}"
            f"{(r.get('lat_shift_deg') or 0):>10.2f}"
            f"{(r.get('spatial_spread_km') or 0):>11,.0f}"
            f"{(r.get('months_with_data') or 0):>8}"
            f"{(r.get('total_records') or 0):>8,}"
            f"{(f'{frac:.1%}' if frac is not None else '-'):>9}"
        )
    return "\n".join(lines)
