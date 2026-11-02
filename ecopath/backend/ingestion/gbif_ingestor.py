"""
EcoPath — GBIF Species Ingestion Engine
=============================================
Builds the species catalogue and population time series from GBIF.

Pipeline:
1. Repair species keys — re-resolve every existing row's `gbif_key` from its
   scientific name. Hand-written seeds carried unverified keys that pointed at
   entirely different taxa (the "White-rumped Vulture" key was a Herring Gull),
   so every downstream fetch for those species pulled the wrong data or 404'd.
2. Build the catalogue — every bird species GBIF holds Indian occurrences for.
3. Ingest population records — exact yearly counts per state, read from GBIF's
   facet totals rather than sampled occurrence points.
4. Trigger PostgreSQL anomaly detection over the fresh series.

Usage:
  python -m ingestion.gbif_ingestor                  # Full run (2015-2024)
  python -m ingestion.gbif_ingestor --dry-run        # Validate, write nothing
  python -m ingestion.gbif_ingestor --limit 50       # Cap catalogue size
  python -m ingestion.gbif_ingestor --skip-catalogue # Populations only
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Optional

# Add backend root to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.repository import fetch_all
from data.sources import gbif
from services.supabase_client import get_supabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("ingestion.log")],
)
logger = logging.getLogger("ecopath.ingestion")

VALID_IUCN = {"LC", "NT", "VU", "EN", "CR", "EW", "EX", "DD", "NE"}

# Curated fields that were written by hand and must survive re-ingestion.
CURATED_FIELDS = (
    "description", "fun_fact", "primary_habitat", "primary_range",
    "endemic_india", "migratory", "image_url", "xeno_canto_id",
)

# GBIF is generous but not unlimited; keep concurrent requests modest.
GBIF_CONCURRENCY = 5
BATCH_SIZE = 500

# Full-table reads page through `data.repository.fetch_all`; PostgREST caps an
# unbounded select at 1000 rows and the catalogue is larger than that.


class GBIFIngestor:
    def __init__(
        self,
        dry_run: bool = False,
        limit: Optional[int] = None,
        year_start: int = 2015,
        year_end: int = 2024,
        skip_catalogue: bool = False,
        skip_populations: bool = False,
    ):
        self.dry_run = dry_run
        self.limit = limit
        self.year_start = year_start
        self.year_end = year_end
        self.skip_catalogue = skip_catalogue
        self.skip_populations = skip_populations
        self.supabase = get_supabase()
        self.sem = asyncio.Semaphore(GBIF_CONCURRENCY)

        self.stats = {
            "keys_repaired": 0,
            "species_inserted": 0,
            "species_updated": 0,
            "species_skipped": 0,
            "records_inserted": 0,
            "regions_processed": 0,
            "start_time": time.time(),
        }

    # ─── Orchestration ──────────────────────────────────────────────────────

    async def run(self):
        logger.info("=" * 62)
        logger.info("EcoPath GBIF Ingestion Engine")
        logger.info(f"   Mode:  {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"   Years: {self.year_start}-{self.year_end}")
        logger.info(f"   Limit: {self.limit or 'none'}")
        logger.info("=" * 62)

        await self.repair_species_keys()

        if not self.skip_catalogue:
            await self.build_catalogue()
        else:
            logger.info("Skipping catalogue build (--skip-catalogue)")

        if not self.skip_populations:
            await self.ingest_populations()
        else:
            logger.info("Skipping population ingest (--skip-populations)")

        await self.detect_anomalies()
        self._print_summary()

    # ─── Step 1: Repair wrong species keys ──────────────────────────────────

    async def repair_species_keys(self):
        """
        Re-resolve every existing row's gbif_key from its scientific name.

        Rows are moved to negative sentinel keys first so that corrected keys
        can be written in any order without tripping the UNIQUE constraint —
        a wrong key may well be another species' correct one.
        """
        logger.info("── Step 1: Repairing species keys ──")
        rows = fetch_all(
            lambda: self.supabase.table("species").select(
                "id, gbif_key, common_name, scientific_name"
            )
        )
        logger.info(f"Checking {len(rows)} existing species rows")

        async def resolve(row):
            async with self.sem:
                res = await gbif.match_species_key(row["scientific_name"])
                return row, (res.data if res.ok else None)

        resolved = await asyncio.gather(*(resolve(r) for r in rows))

        # Keep the first row claiming a key; later duplicates are dropped.
        claimed: dict[int, str] = {}
        fixes: list[tuple[str, int]] = []
        drops: list[str] = []

        for row, key in resolved:
            if key is None:
                logger.warning(f"  no GBIF match for {row['scientific_name']!r} — leaving as is")
                continue
            if key in claimed:
                logger.warning(
                    f"  {row['common_name']!r} resolves to key {key}, already held by "
                    f"{claimed[key]!r} — dropping duplicate row"
                )
                drops.append(row["id"])
                continue
            claimed[key] = row["common_name"]
            if row["gbif_key"] != key:
                logger.info(f"  {row['common_name']:30s} {row['gbif_key']} -> {key}")
                fixes.append((row["id"], key))

        logger.info(f"{len(fixes)} keys need correction, {len(drops)} duplicate rows to drop")
        if self.dry_run:
            self.stats["keys_repaired"] = len(fixes)
            return

        for row_id in drops:
            self.supabase.table("species").delete().eq("id", row_id).execute()

        # Two-phase write: park on negative sentinels, then assign real keys.
        for i, (row_id, _) in enumerate(fixes):
            self.supabase.table("species").update({"gbif_key": -(i + 1)}).eq("id", row_id).execute()
        for row_id, key in fixes:
            self.supabase.table("species").update({"gbif_key": key}).eq("id", row_id).execute()

        self.stats["keys_repaired"] = len(fixes)
        logger.info(f"Repaired {len(fixes)} species keys")

    # ─── Step 2: Build the species catalogue ────────────────────────────────

    async def build_catalogue(self):
        """Insert every Indian bird species GBIF knows about, enriched with IUCN status."""
        logger.info("── Step 2: Building species catalogue ──")

        totals_res = await gbif.all_indian_bird_keys(self.year_start, self.year_end)
        totals = totals_res.data or {}
        if not totals:
            logger.error("GBIF returned no species inventory; aborting catalogue build")
            return

        keys = sorted(totals, key=lambda k: totals[k], reverse=True)
        if self.limit:
            keys = keys[: self.limit]
        logger.info(f"Enriching {len(keys)} species from GBIF")

        existing = fetch_all(
            lambda: self.supabase.table("species").select(
                "id, gbif_key, iucn_status, family, order_name"
            )
        )
        by_key = {r["gbif_key"]: r for r in existing}

        async def enrich(key: int):
            async with self.sem:
                detail_res = await gbif.species_detail(key)
                if not detail_res.ok or detail_res.data is None:
                    return None
                detail = dict(detail_res.data)
                if detail.get("rank") != "SPECIES":
                    return None
                iucn_res = await gbif.iucn_category(key)
                detail["iucn_status"] = iucn_res.data if iucn_res.ok else None
                return detail

        details = await asyncio.gather(*(enrich(k) for k in keys))

        to_insert, updates = [], []
        for detail in details:
            if detail is None or not detail.get("scientific_name"):
                self.stats["species_skipped"] += 1
                continue

            status = detail["iucn_status"] if detail["iucn_status"] in VALID_IUCN else None
            row = by_key.get(detail["gbif_key"])

            if row:
                # Existing row: fill gaps only, never overwrite curated content.
                patch = {}
                if status and not row.get("iucn_status"):
                    patch["iucn_status"] = status
                if detail.get("family") and not row.get("family"):
                    patch["family"] = detail["family"]
                if detail.get("order_name") and not row.get("order_name"):
                    patch["order_name"] = detail["order_name"]
                if patch:
                    updates.append((row["id"], patch))
                continue

            to_insert.append({
                "gbif_key": detail["gbif_key"],
                "common_name": detail.get("common_name") or detail["scientific_name"],
                "scientific_name": detail["scientific_name"],
                "family": detail.get("family"),
                "order_name": detail.get("order_name"),
                "class_name": "Aves",
                "iucn_status": status,
            })

        logger.info(f"{len(to_insert)} new species, {len(updates)} existing rows to enrich")
        if self.dry_run:
            self.stats["species_inserted"] = len(to_insert)
            self.stats["species_updated"] = len(updates)
            return

        for i in range(0, len(to_insert), BATCH_SIZE):
            batch = to_insert[i : i + BATCH_SIZE]
            try:
                self.supabase.table("species").upsert(batch, on_conflict="gbif_key").execute()
                self.stats["species_inserted"] += len(batch)
                logger.info(f"  inserted {len(batch)} species")
            except Exception as e:
                logger.error(f"  species batch failed: {e}")

        for row_id, patch in updates:
            try:
                self.supabase.table("species").update(patch).eq("id", row_id).execute()
                self.stats["species_updated"] += 1
            except Exception as e:
                logger.error(f"  species update {row_id} failed: {e}")

    # ─── Step 3: Population records ─────────────────────────────────────────

    async def ingest_populations(self):
        """
        One record per (species, year, state) holding GBIF's exact occurrence
        total. Costs regions x years requests regardless of species count.
        """
        logger.info("── Step 3: Ingesting population records ──")

        regions_res = await gbif.gadm_subdivisions()
        regions = regions_res.data or {}
        if not regions:
            logger.error("No GADM regions resolved; aborting population ingest")
            return

        species_rows = fetch_all(
            lambda: self.supabase.table("species").select("id, gbif_key")
        )
        key_to_id = {r["gbif_key"]: r["id"] for r in species_rows if r["gbif_key"] > 0}
        logger.info(f"{len(regions)} regions x {self.year_end - self.year_start + 1} years "
                    f"against {len(key_to_id)} known species")

        years = list(range(self.year_start, self.year_end + 1))

        async def fetch(gid: str, year: int):
            async with self.sem:
                res = await gbif.region_year_species_counts(gid, year)
                return gid, year, (res.data or {})

        tasks = [fetch(gid, year) for gid in regions for year in years]
        results = await asyncio.gather(*tasks)

        # Disputed gids share a state name with an IND.* gid, so counts are
        # summed per (species, year, state) before writing.
        merged: dict[tuple[str, int, str], int] = {}
        unknown_keys = set()
        for gid, year, counts in results:
            state = regions[gid]
            for key, count in counts.items():
                species_id = key_to_id.get(key)
                if species_id is None:
                    unknown_keys.add(key)
                    continue
                merged[(species_id, year, state)] = merged.get((species_id, year, state), 0) + count
            self.stats["regions_processed"] += 1

        if unknown_keys:
            logger.info(f"{len(unknown_keys)} observed species keys are not in the catalogue "
                        f"(raise --limit to include them)")

        records = [
            {
                "species_id": sid,
                "year": year,
                "observation_count": count,
                "state_name": state,
                "data_source": "GBIF",
            }
            for (sid, year, state), count in merged.items()
        ]
        logger.info(f"Prepared {len(records)} population records")

        if self.dry_run:
            self.stats["records_inserted"] = len(records)
            return

        # The previous ingest wrote sampled point-records that cap every
        # species at 200/year; they must not survive alongside real totals.
        # Deleted year by year — a single unbounded delete over tens of
        # thousands of rows exceeds PostgREST's statement timeout.
        logger.info("Clearing previously ingested GBIF population records")
        for year in range(2010, 2031):
            try:
                self.supabase.table("population_records").delete().eq(
                    "data_source", "GBIF"
                ).eq("year", year).execute()
            except Exception as e:
                logger.error(f"  failed clearing year {year}: {e}")

        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i : i + BATCH_SIZE]
            try:
                self.supabase.table("population_records").insert(batch).execute()
                self.stats["records_inserted"] += len(batch)
                if (i // BATCH_SIZE) % 20 == 0:
                    logger.info(f"  {self.stats['records_inserted']}/{len(records)} records written")
            except Exception as e:
                logger.error(f"  population batch failed: {e}")

    # ─── Step 4: Anomaly detection ──────────────────────────────────────────

    async def detect_anomalies(self):
        logger.info("── Step 4: Running anomaly detection ──")
        if self.dry_run:
            logger.info("  [dry run] skipped")
            return
        try:
            # Detection inserts with ON CONFLICT DO NOTHING but the table had no
            # matching unique constraint, so re-running it duplicated every row.
            # 06_agent_functions.sql adds the constraint; clearing first keeps
            # the run correct even on a database where it has not been applied.
            for year in range(self.year_start, self.year_end + 1):
                self.supabase.table("anomalies").delete().eq("year", year).execute()

            result = self.supabase.rpc(
                "run_anomaly_detection", {"p_start_year": self.year_start + 3}
            ).execute()
            logger.info(f"  detection returned {len(result.data or [])} rows (page-limited)")
        except Exception as e:
            logger.error(f"  anomaly detection failed: {e}")

    # ─── Reporting ──────────────────────────────────────────────────────────

    def _print_summary(self):
        elapsed = time.time() - self.stats["start_time"]
        logger.info("=" * 62)
        logger.info("Ingestion complete")
        logger.info(f"  Species keys repaired : {self.stats['keys_repaired']}")
        logger.info(f"  Species inserted      : {self.stats['species_inserted']}")
        logger.info(f"  Species enriched      : {self.stats['species_updated']}")
        logger.info(f"  Species skipped       : {self.stats['species_skipped']}")
        logger.info(f"  Region-years fetched  : {self.stats['regions_processed']}")
        logger.info(f"  Population records    : {self.stats['records_inserted']}")
        logger.info(f"  Elapsed               : {elapsed / 60:.1f} min")
        logger.info("=" * 62)


def main():
    parser = argparse.ArgumentParser(description="EcoPath GBIF ingestion engine")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    parser.add_argument("--limit", type=int, default=None, help="Max species in catalogue")
    parser.add_argument("--year-start", type=int, default=2015)
    parser.add_argument("--year-end", type=int, default=2024)
    parser.add_argument("--skip-catalogue", action="store_true")
    parser.add_argument("--skip-populations", action="store_true")
    args = parser.parse_args()

    ingestor = GBIFIngestor(
        dry_run=args.dry_run,
        limit=args.limit,
        year_start=args.year_start,
        year_end=args.year_end,
        skip_catalogue=args.skip_catalogue,
        skip_populations=args.skip_populations,
    )
    asyncio.run(ingestor.run())


if __name__ == "__main__":
    main()
