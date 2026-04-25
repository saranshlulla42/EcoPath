-- ============================================================
-- EcoPath Database: Step 2 — Core Schema
-- Run after 01_extensions.sql
-- ============================================================

-- ─── SPECIES ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS species (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gbif_key            INTEGER UNIQUE NOT NULL,
    common_name         TEXT NOT NULL,
    scientific_name     TEXT NOT NULL,
    family              TEXT,
    order_name          TEXT,
    class_name          TEXT DEFAULT 'Aves',
    iucn_status         TEXT CHECK (iucn_status IN ('LC','NT','VU','EN','CR','EW','EX','DD','NE')),
    endemic_india       BOOLEAN DEFAULT false,
    migratory           BOOLEAN DEFAULT false,
    primary_habitat     TEXT[],               -- e.g. ARRAY['wetland', 'forest']
    primary_range       TEXT[],               -- e.g. ARRAY['Pan-India', 'Western Ghats']
    image_url           TEXT,                 -- Supabase Storage URL
    gbif_image_url      TEXT,                 -- Direct GBIF media URL
    xeno_canto_id       TEXT,                 -- xeno-canto recording ID
    description         TEXT,                 -- AI-generated or GBIF description
    fun_fact            TEXT,
    gbif_occurrence_url TEXT,
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Trigram index for fast fuzzy name search (autocomplete)
CREATE INDEX IF NOT EXISTS idx_species_common_name_trgm
    ON species USING GIN (common_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_species_scientific_name_trgm
    ON species USING GIN (scientific_name gin_trgm_ops);

-- ─── POPULATION RECORDS ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS population_records (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id          UUID NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    year                SMALLINT NOT NULL CHECK (year BETWEEN 2010 AND 2030),
    month               SMALLINT CHECK (month BETWEEN 1 AND 12),
    observation_count   INTEGER NOT NULL DEFAULT 0,
    location            GEOGRAPHY(Point, 4326),    -- PostGIS geographic point
    state_name          TEXT,
    district            TEXT,
    data_source         TEXT DEFAULT 'GBIF',
    gbif_dataset_key    TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Spatial index for geography queries
CREATE INDEX IF NOT EXISTS idx_population_location
    ON population_records USING GIST (location);

-- Composite index for time-series queries
CREATE INDEX IF NOT EXISTS idx_population_species_year
    ON population_records (species_id, year);

CREATE INDEX IF NOT EXISTS idx_population_state_year
    ON population_records (state_name, year);

-- ─── ANOMALIES ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomalies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id          UUID NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    year                SMALLINT NOT NULL,
    anomaly_type        TEXT NOT NULL CHECK (anomaly_type IN ('surge', 'dip', 'local_extinction', 'recolonization')),
    magnitude_pct       NUMERIC(8, 2),          -- % deviation from 5-yr rolling avg
    severity            TEXT CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    affected_state      TEXT,
    observed_count      INTEGER,
    expected_count      INTEGER,
    rolling_avg_5yr     NUMERIC(10, 2),
    causal_hypothesis   TEXT,                   -- Gemini 1.5 Pro generated
    weather_context     JSONB,                  -- Open-Meteo snapshot
    supporting_evidence TEXT[],                 -- e.g. ['drought 2019', 'cyclone Ockhi']
    confidence_score    NUMERIC(4, 2),          -- 0.0 - 1.0
    detected_at         TIMESTAMPTZ DEFAULT NOW(),
    reviewed            BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_anomalies_species_year
    ON anomalies (species_id, year);

CREATE INDEX IF NOT EXISTS idx_anomalies_type
    ON anomalies (anomaly_type, severity);

-- ─── MIGRATION ROUTES ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS migration_routes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    species_id          UUID NOT NULL REFERENCES species(id) ON DELETE CASCADE,
    route_name          TEXT NOT NULL,
    flyway              TEXT,                   -- e.g. 'Central Asian Flyway'
    season              TEXT CHECK (season IN ('winter','summer','monsoon','post-monsoon','year-round')),
    direction           TEXT CHECK (direction IN ('north-south','south-north','east-west','west-east','circular')),
    route_geom          GEOGRAPHY(LineString, 4326),  -- PostGIS LineString
    waypoints           JSONB,                  -- [{lat, lng, month, description, location_name}]
    active_months       INTEGER[],              -- e.g. ARRAY[10,11,12,1] for winter
    distance_km         NUMERIC(8, 1),
    source              TEXT DEFAULT 'GBIF',    -- 'BirdLife' | 'GBIF' | 'Manual'
    verified            BOOLEAN DEFAULT false,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_migration_species
    ON migration_routes (species_id);

CREATE INDEX IF NOT EXISTS idx_migration_geom
    ON migration_routes USING GIST (route_geom);

-- ─── ROW-LEVEL SECURITY ──────────────────────────────────────────────────────
ALTER TABLE species ENABLE ROW LEVEL SECURITY;
ALTER TABLE population_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE anomalies ENABLE ROW LEVEL SECURITY;
ALTER TABLE migration_routes ENABLE ROW LEVEL SECURITY;

-- Allow public read access (dashboard is read-only for anon users)
CREATE POLICY "public_read_species" ON species FOR SELECT USING (true);
CREATE POLICY "public_read_population" ON population_records FOR SELECT USING (true);
CREATE POLICY "public_read_anomalies" ON anomalies FOR SELECT USING (true);
CREATE POLICY "public_read_migration" ON migration_routes FOR SELECT USING (true);

-- Service role can do everything (used by backend ingestion engine)
CREATE POLICY "service_write_species" ON species
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write_population" ON population_records
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write_anomalies" ON anomalies
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "service_write_migration" ON migration_routes
    FOR ALL USING (auth.role() = 'service_role');

-- ─── UPDATED_AT TRIGGER ──────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_species_updated_at
    BEFORE UPDATE ON species
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
