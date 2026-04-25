"""
EcoPath — GBIF Species Ingestion Engine
=============================================
Autonomous ingestion pipeline that:
1. Fetches Indian bird species from the GBIF API
2. Enriches each with taxonomic metadata and media
3. Upserts into Supabase `species` and `population_records` tables
4. Triggers PostgreSQL anomaly detection on completion

Usage:
  python gbif_ingestor.py                     # Full run (all species, 2015-2024)
  python gbif_ingestor.py --dry-run           # Validate without writing to DB
  python gbif_ingestor.py --limit 20          # Process first 20 species
  python gbif_ingestor.py --year-start 2020  # Start from a specific year
"""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add backend root to path for config imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from services.gbif_client import (
    fetch_indian_bird_species_keys,
    get_species_by_key,
    get_species_media,
    get_occurrence_counts_by_year,
    get_occurrence_points,
)
from services.supabase_client import get_supabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ingestion.log"),
    ]
)
logger = logging.getLogger("ecopath.ingestion")

settings = get_settings()

# ─── IUCN Status Mapping ────────────────────────────────────────────────────
# GBIF doesn't directly expose IUCN status; we map by family/species
IUCN_OVERRIDES = {
    "Ardeotis nigriceps": "CR",
    "Houbaropsis bengalensis": "CR",
    "Gyps indicus": "CR",
    "Gyps bengalensis": "CR",
    "Liocichla bugunorum": "CR",
    "Rhinoptilus bitorquatus": "CR",
    "Vanellus gregarius": "CR",
    "Athene blewitti": "EN",
    "Montecincla cachinnans": "EN",
    "Anastomus oscitans": "LC",
    "Falco amurensis": "LC",
}

# ─── Migratory Species Keys (known migrants to India) ──────────────────────
MIGRATORY_KEYS = {
    2481064,  # Amur Falcon
    2460912,  # Bar-headed Goose
    2481060,  # Demoiselle Crane
    2474887,  # Ruddy Shelduck
    2481045,  # Common Pochard
    2480978,  # Greater Flamingo
    2481029,  # Lesser Flamingo
    2480432,  # Dalmatian Pelican
}


class GBIFIngestor:
    def __init__(
        self,
        dry_run: bool = False,
        limit: Optional[int] = None,
        year_start: int = 2015,
        year_end: int = 2024,
    ):
        self.dry_run = dry_run
        self.limit = limit
        self.year_start = year_start
        self.year_end = year_end
        self.supabase = get_supabase()

        # Stats
        self.stats = {
            "species_processed": 0,
            "species_upserted": 0,
            "species_failed": 0,
            "records_upserted": 0,
            "records_failed": 0,
            "start_time": time.time(),
        }

    async def run(self):
        logger.info("=" * 60)
        logger.info("🦜 EcoPath GBIF Ingestion Engine Starting")
        logger.info(f"   Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"   Limit: {self.limit or 'Unlimited'}")
        logger.info(f"   Year Range: {self.year_start} - {self.year_end}")
        logger.info("=" * 60)

        # Step 1: Get seeded species from our DB (process those first)
        seeded_keys = await self._get_seeded_gbif_keys()
        logger.info(f"Found {len(seeded_keys)} pre-seeded species in DB")

        # Step 2: Fetch full list from GBIF
        all_keys = await fetch_indian_bird_species_keys(limit=self.limit or 200)

        # Prioritize seeded species
        priority_keys = [k for k in seeded_keys if k in all_keys]
        remaining_keys = [k for k in all_keys if k not in seeded_keys]
        ordered_keys = priority_keys + remaining_keys

        if self.limit:
            ordered_keys = ordered_keys[:self.limit]

        logger.info(f"Processing {len(ordered_keys)} species total")
        logger.info(f"  Priority (seeded): {len(priority_keys)}")
        logger.info(f"  Additional GBIF:   {len(remaining_keys[:self.limit or 1000])}")

        # Step 3: Process each species
        for i, gbif_key in enumerate(ordered_keys, 1):
            logger.info(f"[{i}/{len(ordered_keys)}] Processing species key: {gbif_key}")
            try:
                species_id = await self._ingest_species(gbif_key)
                if species_id:
                    await self._ingest_population_records(species_id, gbif_key)
                    self.stats["species_processed"] += 1
                    # Polite delay
                    await asyncio.sleep(1.0)
            except Exception as e:
                logger.error(f"  ❌ Failed to process {gbif_key}: {e}")
                self.stats["species_failed"] += 1
                continue

        # Step 4: Run anomaly detection
        if not self.dry_run and self.stats["records_upserted"] > 0:
            await self._run_anomaly_detection()

        self._print_summary()

    async def _get_seeded_gbif_keys(self) -> list[int]:
        """Get GBIF keys of species already in our DB."""
        try:
            result = self.supabase.table("species").select("gbif_key").execute()
            return [row["gbif_key"] for row in (result.data or [])]
        except Exception as e:
            logger.error(f"Failed to fetch seeded keys: {e}")
            return []

    async def _ingest_species(self, gbif_key: int) -> Optional[str]:
        """
        Fetch GBIF metadata and upsert into species table.
        Returns the Supabase UUID if successful.
        """
        metadata = await get_species_by_key(gbif_key)
        if not metadata:
            logger.warning(f"  No metadata found for key {gbif_key}")
            return None

        # Only process accepted species in class Aves
        if metadata.get("class") != "Aves":
            logger.debug(f"  Skipping non-bird key {gbif_key}")
            return None

        if metadata.get("taxonomicStatus") not in ("ACCEPTED", "DOUBTFUL"):
            logger.debug(f"  Skipping synonym key {gbif_key}")
            return None

        scientific_name = metadata.get("canonicalName") or metadata.get("scientificName", "")
        common_name = metadata.get("vernacularName") or metadata.get("canonicalName", "Unknown")

        # Fetch media (bird image)
        media_list = await get_species_media(gbif_key, limit=3)
        gbif_image_url = None
        for m in media_list:
            if m.get("type") == "StillImage" and m.get("identifier"):
                gbif_image_url = m["identifier"]
                break

        species_data = {
            "gbif_key": gbif_key,
            "common_name": common_name,
            "scientific_name": scientific_name,
            "family": metadata.get("family"),
            "order_name": metadata.get("order"),
            "class_name": "Aves",
            "iucn_status": IUCN_OVERRIDES.get(scientific_name, "LC"),
            "endemic_india": False,  # Will be enriched in Phase 2
            "migratory": gbif_key in MIGRATORY_KEYS,
            "primary_habitat": [],
            "primary_range": ["India"],
            "gbif_image_url": gbif_image_url,
            "gbif_occurrence_url": f"https://www.gbif.org/species/{gbif_key}",
            "updated_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"  📋 {common_name} ({scientific_name})")

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would upsert species: {common_name}")
            self.stats["species_upserted"] += 1
            return "dry-run-id"

        try:
            result = (
                self.supabase.table("species")
                .upsert(species_data, on_conflict="gbif_key")
                .execute()
            )
            if result.data:
                self.stats["species_upserted"] += 1
                return result.data[0]["id"]
        except Exception as e:
            logger.error(f"  ❌ Upsert failed for {common_name}: {e}")
            self.stats["species_failed"] += 1

        return None

    async def _ingest_population_records(
        self,
        species_id: str,
        gbif_key: int,
    ):
        """
        Fetch yearly occurrence counts and spatial points from GBIF.
        Upserts into population_records table.
        """
        logger.info(f"  📊 Fetching occurrence data for years {self.year_start}-{self.year_end}...")

        yearly_counts = await get_occurrence_counts_by_year(
            gbif_key,
            self.year_start,
            self.year_end,
        )

        records_to_upsert = []

        for year_data in yearly_counts:
            year = year_data["year"]
            total_count = year_data["count"]

            if total_count == 0:
                continue

            # Fetch actual points for significant observation years (>50 records)
            if total_count >= 50:
                points = await get_occurrence_points(gbif_key, year, limit=200)
                await asyncio.sleep(0.5)  # Rate limit courtesy delay

                for point in points:
                    records_to_upsert.append({
                        "species_id": species_id,
                        "year": year,
                        "month": point.get("month"),
                        "observation_count": 1,
                        "state_name": point.get("state", "Unknown"),
                        "data_source": "GBIF",
                    })
            else:
                # For low-count years, store aggregate only (no coordinates)
                records_to_upsert.append({
                    "species_id": species_id,
                    "year": year,
                    "observation_count": total_count,
                    "state_name": "Pan-India",
                    "data_source": "GBIF",
                })

            logger.info(f"    Year {year}: {total_count} observations → {len(records_to_upsert)} records queued")

        if not records_to_upsert:
            logger.info("    No records to insert")
            return

        if self.dry_run:
            logger.info(f"  [DRY RUN] Would insert {len(records_to_upsert)} population records")
            self.stats["records_upserted"] += len(records_to_upsert)
            return

        # Batch upsert in chunks of 500
        BATCH_SIZE = 500
        for i in range(0, len(records_to_upsert), BATCH_SIZE):
            batch = records_to_upsert[i:i + BATCH_SIZE]
            try:
                self.supabase.table("population_records").insert(batch).execute()
                self.stats["records_upserted"] += len(batch)
                logger.info(f"  ✅ Inserted batch of {len(batch)} records")
            except Exception as e:
                logger.error(f"  ❌ Batch insert failed: {e}")
                self.stats["records_failed"] += len(batch)

    async def _run_anomaly_detection(self):
        """Trigger PostgreSQL anomaly detection after ingestion completes."""
        logger.info("\n🔬 Running anomaly detection...")
        try:
            result = self.supabase.rpc(
                "run_anomaly_detection",
                {"p_start_year": self.year_start},
            ).execute()
            anomalies = result.data or []
            logger.info(f"  ✅ Detected {len(anomalies)} anomalies")
        except Exception as e:
            logger.error(f"  ❌ Anomaly detection failed: {e}")

    def _print_summary(self):
        elapsed = time.time() - self.stats["start_time"]
        logger.info("\n" + "=" * 60)
        logger.info("🦜 EcoPath GBIF Ingestion Complete")
        logger.info(f"   Total time:        {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        logger.info(f"   Species processed: {self.stats['species_processed']}")
        logger.info(f"   Species upserted:  {self.stats['species_upserted']}")
        logger.info(f"   Species failed:    {self.stats['species_failed']}")
        logger.info(f"   Records upserted:  {self.stats['records_upserted']}")
        logger.info(f"   Records failed:    {self.stats['records_failed']}")
        if self.dry_run:
            logger.info("   Mode: DRY RUN — no data was written to the database")
        logger.info("=" * 60)


# ─── Entry Point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EcoPath GBIF Ingestion Engine")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to DB")
    parser.add_argument("--limit", type=int, default=None, help="Max number of species to process")
    parser.add_argument("--year-start", type=int, default=2015, help="Start year for occurrence data")
    parser.add_argument("--year-end", type=int, default=2024, help="End year for occurrence data")
    args = parser.parse_args()

    ingestor = GBIFIngestor(
        dry_run=args.dry_run,
        limit=args.limit,
        year_start=args.year_start,
        year_end=args.year_end,
    )

    asyncio.run(ingestor.run())
