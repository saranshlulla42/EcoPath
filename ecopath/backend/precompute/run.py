#!/usr/bin/env python
"""CLI for the offline migration precomputation.

    python -m precompute.run harvest --sample 40      # fetch points from GBIF
    python -m precompute.run compute                  # metrics + H3, no network
    python -m precompute.run distributions            # stats for setting cutoffs
    python -m precompute.run classify --migratory-above-km 475 \
        --resident-below-km 350 --min-records 100 --min-months 6

`classify` deliberately has no default thresholds and refuses to run without
them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from precompute import distributions, fetch, hexes, known, pipeline, store  # noqa: E402
from precompute.classify import Status, Thresholds, classify  # noqa: E402
from precompute.metrics import SpeciesMetrics  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ecopath.precompute")

DEFAULT_YEARS = list(range(2015, 2025))


def _record_counts(sb) -> dict[str, int]:
    """Local population_records count per species, as a sparsity proxy."""
    from collections import Counter

    counts: Counter[str] = Counter()
    offset = 0
    while True:
        batch = (
            sb.table("population_records").select("species_id")
            .range(offset, offset + 999).execute().data or []
        )
        if not batch:
            break
        counts.update(r["species_id"] for r in batch)
        offset += 1000
    return dict(counts)


def load_refs(sample: int | None = None, labelled_only: bool = False,
              sparse: int | None = None) -> list[fetch.SpeciesRef]:
    """Species to process, from the Supabase catalogue."""
    from services.supabase_client import get_supabase

    sb = get_supabase()
    rows: list[dict] = []
    offset = 0
    while True:
        batch = (
            sb.table("species")
            .select("id,gbif_key,scientific_name,common_name,migratory")
            .range(offset, offset + 999)
            .execute()
            .data
            or []
        )
        if not batch:
            break
        rows.extend(batch)
        offset += 1000

    rows = [r for r in rows if r.get("gbif_key")]

    if sparse:
        # The thin end of the distribution, which the well-sampled validation
        # set cannot reach. Record counts here come from GBIF facet totals, so
        # they are a sound proxy for how little GBIF holds.
        counts = _record_counts(sb)
        rows.sort(key=lambda r: counts.get(r["id"], 0))
        rows = rows[:sparse]
    elif labelled_only:
        # The validation set: species whose answer is not in doubt. Read from
        # `known.py`, not from the catalogue's `migratory` column, which is
        # False for 1,402 of 1,413 species by default rather than by judgement.
        by_name = {r.get("common_name"): r for r in rows}
        rows = [by_name[n] for n in known.ALL_KNOWN if n in by_name]
    elif sample:
        rows = rows[:sample]

    return [
        fetch.SpeciesRef(
            species_id=r["id"],
            gbif_key=r.get("gbif_key"),
            scientific_name=r.get("scientific_name") or "",
            common_name=r.get("common_name") or "",
            migratory=r.get("migratory"),
        )
        for r in rows
    ]


def metric_rows(conn) -> list[dict]:
    cols = [
        "species_id", "scientific_name", "common_name", "catalogue_migratory",
        "total_records", "points_with_month", "months_with_data",
        "max_displacement_km", "displacement_months", "lat_shift_deg",
        "lat_range_deg", "spatial_spread_km", "effort_index", "effort_basis",
        "sampling_fraction",
    ]
    rows = conn.execute(f"SELECT {','.join(cols)} FROM species_metrics").fetchall()
    out = [dict(zip(cols, r)) for r in rows]
    # Ground truth comes from the explicit validation set, never from the
    # catalogue's `migratory` column — see precompute/known.py.
    for r in out:
        r["known_status"] = known.known_status(r.get("common_name"))
    return out


def cmd_harvest(args) -> int:
    refs = load_refs(args.sample, labelled_only=args.labelled, sparse=args.sparse)
    print(f"harvesting {len(refs)} species, years {DEFAULT_YEARS[0]}-{DEFAULT_YEARS[-1]}")
    print(f"  ~{len(refs) * len(DEFAULT_YEARS)} GBIF requests at concurrency {args.concurrency}")
    if not args.yes:
        if input("proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("aborted.")
            return 1

    done = {"n": 0}

    def progress(ref, n, with_month, error):
        done["n"] += 1
        flag = f"ERR {error[:40]}" if error else ""
        print(f"  [{done['n']}/{len(refs)}] {ref.common_name[:34]:<35} "
              f"{n:>5} pts, {with_month:>5} with month  {flag}")

    stats = asyncio.run(
        fetch.harvest(refs, DEFAULT_YEARS, concurrency=args.concurrency, progress=progress)
    )
    print(f"\n{stats}")
    return 0


def cmd_compute(args) -> int:
    refs = {r.species_id: r for r in load_refs()}
    conn = store.connect()
    ids = [r[0] for r in conn.execute("SELECT species_id FROM harvest_log").fetchall()]
    n = 0
    for sid in ids:
        ref = refs.get(sid)
        pipeline.compute_species(
            conn,
            sid,
            scientific_name=ref.scientific_name if ref else "",
            common_name=ref.common_name if ref else "",
            catalogue_migratory=ref.migratory if ref else None,
            resolution=args.resolution,
        )
        n += 1
    hexcount = conn.execute("SELECT COUNT(*) FROM species_month_hex").fetchone()[0]
    print(f"computed metrics for {n} species; {hexcount} hex cells at res {args.resolution}")
    conn.close()
    return 0


def cmd_distributions(args) -> int:
    conn = store.connect(read_only=True)
    rows = metric_rows(conn)
    conn.close()
    if not rows:
        print("No metrics yet. Run: python -m precompute.run harvest --sample 40 && "
              "python -m precompute.run compute")
        return 1
    print(distributions.metric_report(rows))
    print(distributions.known_species_table(rows, limit=args.limit))
    return 0


def cmd_classify(args) -> int:
    missing = [
        name
        for name, value in (
            ("--migratory-above-km", args.migratory_above_km),
            ("--resident-below-km", args.resident_below_km),
            ("--min-records", args.min_records),
            ("--min-months", args.min_months),
        )
        if value is None
    ]
    if missing:
        print(
            "Refusing to classify without thresholds. Missing: "
            + ", ".join(missing)
            + "\nRun `distributions` first and choose them from the data.",
            file=sys.stderr,
        )
        return 2

    if args.resident_below_km > args.migratory_above_km:
        print("resident-below-km must not exceed migratory-above-km", file=sys.stderr)
        return 2

    t = Thresholds(
        migratory_above_km=args.migratory_above_km,
        resident_below_km=args.resident_below_km,
        min_records=args.min_records,
        min_months_with_data=args.min_months,
        min_sampling_fraction=args.min_sampling_fraction,
        min_spatial_spread_km=args.min_spread_km,
    )
    conn = store.connect()
    rows = metric_rows(conn)

    tally: dict[str, int] = {}
    written = []
    agree = disagree = 0
    for r in rows:
        m = SpeciesMetrics(
            total_records=r["total_records"] or 0,
            points_with_month=r["points_with_month"] or 0,
            months_with_data=r["months_with_data"] or 0,
            max_displacement_km=r["max_displacement_km"],
            displacement_months=r["displacement_months"],
            lat_shift_deg=r["lat_shift_deg"],
            lat_range_deg=r["lat_range_deg"],
            spatial_spread_km=r["spatial_spread_km"],
            sampling_fraction=r["sampling_fraction"],
        )
        c = classify(m, t)
        key = (f"{c.status.value} ({c.insufficient_basis})"
               if c.insufficient_basis else c.status.value)
        tally[key] = tally.get(key, 0) + 1
        written.append((
            r["species_id"], r.get("common_name"), c.status.value, c.confidence,
            c.insufficient_basis, " | ".join(c.reasons), c.total_records,
            c.months_with_data, c.max_displacement_km, c.sampling_fraction,
            json.dumps(c.thresholds_used), datetime.now(timezone.utc),
        ))
        truth = r.get("known_status")
        if truth is not None and c.status is not Status.INSUFFICIENT_DATA:
            if c.status.value == truth:
                agree += 1
            else:
                disagree += 1

    conn.execute("DELETE FROM species_status")
    conn.executemany(
        "INSERT INTO species_status VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", written
    )
    conn.close()

    print(f"thresholds: {t}")
    print(f"wrote {len(written)} rows to species_status")
    for status, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"  {status:<20} {n:>5}  ({n/len(rows):.1%})")
    if agree + disagree:
        print(f"  agreement with the validation set: {agree}/{agree+disagree} = "
              f"{agree/(agree+disagree):.1%} (insufficient_data excluded)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("harvest", help="fetch occurrence points from GBIF")
    h.add_argument("--sample", type=int, help="only this many species")
    h.add_argument("--sparse", type=int,
                   help="the N species with the fewest local records, to calibrate coverage gates")
    h.add_argument("--labelled", action="store_true",
                   help="only species with a known status (see precompute/known.py)")
    h.add_argument("--concurrency", type=int, default=fetch.DEFAULT_CONCURRENCY)
    h.add_argument("--yes", "-y", action="store_true")
    h.set_defaults(func=cmd_harvest)

    c = sub.add_parser("compute", help="metrics + H3 aggregations from stored points")
    c.add_argument("--resolution", type=int, default=hexes.DEFAULT_RESOLUTION)
    c.set_defaults(func=cmd_compute)

    d = sub.add_parser("distributions", help="stats and histograms for choosing cutoffs")
    d.add_argument("--limit", type=int, default=40)
    d.set_defaults(func=cmd_distributions)

    k = sub.add_parser("classify", help="apply cutoffs (all required)")
    k.add_argument("--migratory-above-km", type=float,
                   help="displacement at or above this is migratory")
    k.add_argument("--resident-below-km", type=float,
                   help="displacement below this is resident; the band between is inconclusive")
    k.add_argument("--min-records", type=int)
    k.add_argument("--min-months", type=int)
    k.add_argument("--min-sampling-fraction", type=float, default=None)
    k.add_argument("--min-spread-km", type=float, default=None)
    k.set_defaults(func=cmd_classify)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
