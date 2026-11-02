"""DuckDB store for precomputed migration metrics.

Why DuckDB: the work here is columnar aggregation over millions of occurrence
points — group by species and month, roll up into H3 cells — which is exactly
what it is built for, and it needs no server, no daemon and no extra
infrastructure. Postgres would mean pushing millions of rows across the wire to
Supabase for data the app only ever reads; SQLite would do the storage but not
the aggregation at a sensible speed.

Everything here is derived data. The file can be deleted and rebuilt from GBIF
at any time, so it is a cache with provenance, not a source of truth.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import duckdb

logger = logging.getLogger("ecopath.precompute.store")

DB_PATH = Path(
    os.getenv("ECOPATH_PRECOMPUTE_DB", Path(__file__).resolve().parent.parent / "precompute.duckdb")
)

SCHEMA = """
-- Raw harvested points. Kept so metrics can be recomputed without re-fetching,
-- which matters because refetching means thousands of GBIF requests.
CREATE TABLE IF NOT EXISTS occurrence_points (
    species_id   TEXT    NOT NULL,
    gbif_key     BIGINT,
    year         SMALLINT,
    month        TINYINT,          -- NULL where GBIF has no month; never guessed
    lat          DOUBLE  NOT NULL,
    lng          DOUBLE  NOT NULL,
    state        TEXT
);

-- What was actually fetched per species, so coverage can distinguish "no data"
-- from "we did not look". Without this, an interrupted harvest looks identical
-- to a genuinely unrecorded species.
CREATE TABLE IF NOT EXISTS harvest_log (
    species_id      TEXT PRIMARY KEY,
    gbif_key        BIGINT,
    scientific_name TEXT,
    common_name     TEXT,
    years_requested TEXT,
    points_fetched  INTEGER,
    points_with_month INTEGER,
    gbif_total      BIGINT,        -- GBIF's own count, for the sampling fraction
    fetched_at      TIMESTAMP,
    error           TEXT
);

-- Per species per month centroid and spread.
CREATE TABLE IF NOT EXISTS monthly_centroids (
    species_id  TEXT     NOT NULL,
    month       TINYINT  NOT NULL,
    n_points    INTEGER  NOT NULL,
    centroid_lat DOUBLE  NOT NULL,
    centroid_lng DOUBLE  NOT NULL,
    lat_min     DOUBLE,
    lat_max     DOUBLE,
    spread_km   DOUBLE,            -- mean distance of points from the centroid
    PRIMARY KEY (species_id, month)
);

-- One row per species: the metrics the classification reads.
-- Deliberately carries no status: classification is a separate, parameterised
-- step so thresholds can change without re-deriving anything.
CREATE TABLE IF NOT EXISTS species_metrics (
    species_id            TEXT PRIMARY KEY,
    scientific_name       TEXT,
    common_name           TEXT,
    catalogue_migratory   BOOLEAN,   -- the curated flag, for validation only
    total_records         INTEGER,
    points_with_month     INTEGER,
    months_with_data      TINYINT,
    max_displacement_km   DOUBLE,    -- max great-circle between monthly centroids
    displacement_months   TEXT,      -- which pair produced it, e.g. "1-7"
    lat_shift_deg         DOUBLE,    -- max minus min monthly centroid latitude
    lat_range_deg         DOUBLE,    -- overall latitudinal extent of all points
    spatial_spread_km     DOUBLE,    -- mean distance of all points from the annual centroid
    effort_index          DOUBLE,    -- coarse sampling-effort proxy; NULL if unavailable
    effort_basis          TEXT,      -- what effort_index was derived from
    sampling_fraction     DOUBLE,    -- points_fetched / gbif_total
    computed_at           TIMESTAMP
);

-- Per species per month H3 aggregation, for map rendering without hitting GBIF.
CREATE TABLE IF NOT EXISTS species_month_hex (
    species_id  TEXT     NOT NULL,
    month       TINYINT  NOT NULL,
    h3_index    TEXT     NOT NULL,
    resolution  TINYINT  NOT NULL,
    n_points    INTEGER  NOT NULL,
    centroid_lat DOUBLE,
    centroid_lng DOUBLE,
    PRIMARY KEY (species_id, month, h3_index, resolution)
);

-- The derived verdict. Separate from species_metrics because thresholds change
-- and metrics do not: re-classifying rewrites only this table.
CREATE TABLE IF NOT EXISTS species_status (
    species_id         TEXT PRIMARY KEY,
    common_name        TEXT,
    status             TEXT NOT NULL,   -- migratory | resident | insufficient_data
    confidence         DOUBLE NOT NULL,
    insufficient_basis TEXT,            -- coverage | inconclusive | NULL
    reasons            TEXT,
    -- Coverage travels with the verdict, always. A status read without these is
    -- exactly the collapse the domain rules forbid.
    total_records      INTEGER,
    months_with_data   TINYINT,
    max_displacement_km DOUBLE,
    sampling_fraction  DOUBLE,
    thresholds_used    TEXT,
    classified_at      TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_points_species ON occurrence_points(species_id);
CREATE INDEX IF NOT EXISTS idx_hex_species_month ON species_month_hex(species_id, month);
"""


def connect(path: Optional[Path] = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(target), read_only=read_only)
    if not read_only:
        conn.execute(SCHEMA)
    return conn


def reset(path: Optional[Path] = None) -> None:
    """Drop and rebuild. Only derived data lives here, so this is always safe."""
    target = Path(path) if path else DB_PATH
    if target.exists():
        target.unlink()
    connect(target).close()
    logger.info("precompute store reset at %s", target)
