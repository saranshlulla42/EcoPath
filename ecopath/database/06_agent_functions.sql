-- ============================================================
-- EcoPath Database: Step 6 — Agent Query Surface
--
-- The chat agent could previously only answer five hard-coded question
-- shapes, all of which required a single named species. These functions give
-- it three things it lacked:
--   1. coverage introspection, so it can state what the database holds
--      instead of speculating when a query comes back empty;
--   2. cross-species aggregation, so "which state has the most endangered
--      birds" is answerable at all;
--   3. a guarded read-only SQL escape hatch for genuinely open questions.
--
-- Run after 05_migration_seed.sql.
-- ============================================================

-- ─── READ-ONLY ROLE ──────────────────────────────────────────────────────────
-- Every agent-authored query executes as this role. It is the real security
-- boundary; the keyword checks below are only a fast first filter.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ecopath_readonly') THEN
        CREATE ROLE ecopath_readonly NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO ecopath_readonly;
GRANT SELECT ON species, population_records, anomalies, migration_routes
    TO ecopath_readonly;

-- Explicitly ensure the role can never write, even if future grants are broad.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public
    FROM ecopath_readonly;

-- service_role must be a member of the role in order to SET ROLE to it.
GRANT ecopath_readonly TO service_role;


-- ─── FUNCTION: Dataset coverage ──────────────────────────────────────────────
-- Grounds the agent in what actually exists. Without this the model invents
-- ecological explanations for what are really gaps in ingestion.

CREATE OR REPLACE FUNCTION dataset_coverage()
RETURNS JSONB
LANGUAGE sql
STABLE
AS $$
    SELECT jsonb_build_object(
        'species_total',        (SELECT COUNT(*) FROM species),
        'species_with_records', (SELECT COUNT(DISTINCT species_id) FROM population_records),
        'population_records',   (SELECT COUNT(*) FROM population_records),
        'anomalies',            (SELECT COUNT(*) FROM anomalies),
        'migration_routes',     (SELECT COUNT(*) FROM migration_routes),
        'year_min',             (SELECT MIN(year) FROM population_records),
        'year_max',             (SELECT MAX(year) FROM population_records),
        'states',               (SELECT COALESCE(jsonb_agg(s ORDER BY s), '[]'::jsonb)
                                   FROM (SELECT DISTINCT state_name AS s
                                           FROM population_records
                                          WHERE state_name IS NOT NULL) d),
        'iucn_breakdown',       (SELECT COALESCE(jsonb_object_agg(status, n), '{}'::jsonb)
                                   FROM (SELECT COALESCE(iucn_status, 'unknown') AS status,
                                                COUNT(*) AS n
                                           FROM species GROUP BY 1) b),
        'threatened_with_data', (SELECT COUNT(DISTINCT s.id)
                                   FROM species s
                                   JOIN population_records p ON p.species_id = s.id
                                  WHERE s.iucn_status IN ('VU','EN','CR'))
    );
$$;


-- ─── FUNCTION: Rank states by a cross-species metric ─────────────────────────
-- Answers "which state has the most endangered birds", "where are observations
-- most concentrated", and similar questions that span the whole catalogue.
--
-- p_metric:
--   'species_richness'  distinct species recorded in the state
--   'observations'      total observation count
--   'threatened_species' distinct species in the requested IUCN categories

CREATE OR REPLACE FUNCTION rank_states(
    p_metric        TEXT     DEFAULT 'species_richness',
    p_iucn_statuses TEXT[]   DEFAULT NULL,
    p_year_start    SMALLINT DEFAULT NULL,
    p_year_end      SMALLINT DEFAULT NULL,
    p_limit         INTEGER  DEFAULT 40
)
RETURNS TABLE (
    state_name       TEXT,
    species_count    BIGINT,
    observation_total BIGINT,
    metric_value     BIGINT
)
LANGUAGE sql
STABLE
AS $$
    WITH filtered AS (
        SELECT p.state_name, p.species_id, p.observation_count
          FROM population_records p
          JOIN species s ON s.id = p.species_id
         WHERE p.state_name IS NOT NULL
           AND (p_year_start IS NULL OR p.year >= p_year_start)
           AND (p_year_end   IS NULL OR p.year <= p_year_end)
           AND (p_iucn_statuses IS NULL OR s.iucn_status = ANY (p_iucn_statuses))
    ),
    agg AS (
        SELECT f.state_name,
               COUNT(DISTINCT f.species_id)      AS species_count,
               SUM(f.observation_count)::BIGINT  AS observation_total
          FROM filtered f
         GROUP BY f.state_name
    )
    SELECT a.state_name,
           a.species_count,
           a.observation_total,
           CASE p_metric
               WHEN 'observations' THEN a.observation_total
               ELSE a.species_count
           END AS metric_value
      FROM agg a
     ORDER BY metric_value DESC NULLS LAST
     LIMIT p_limit;
$$;


-- ─── FUNCTION: Guarded read-only SQL ─────────────────────────────────────────
-- The escape hatch for questions the typed tools do not cover. Defence is
-- layered: a shape check, a keyword denylist, a hard row cap, a statement
-- timeout, and — the part that actually matters — execution under a role with
-- no write privileges.

CREATE OR REPLACE FUNCTION exec_readonly_sql(
    p_query     TEXT,
    p_row_limit INTEGER DEFAULT 500
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
DECLARE
    cleaned TEXT := btrim(p_query, E' \t\r\n;');
    result  JSONB;
BEGIN
    IF cleaned IS NULL OR cleaned = '' THEN
        RAISE EXCEPTION 'Empty query';
    END IF;

    IF cleaned !~* '^\s*(select|with)\s' THEN
        RAISE EXCEPTION 'Only SELECT or WITH queries are permitted';
    END IF;

    -- Trailing semicolons were stripped above, so any remaining one means a
    -- second statement is being smuggled in.
    IF position(';' IN cleaned) > 0 THEN
        RAISE EXCEPTION 'Multiple statements are not permitted';
    END IF;

    IF cleaned ~* '\m(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze|call|do|reset|listen|notify|prepare|execute|refresh|comment|lock|set)\M' THEN
        RAISE EXCEPTION 'Query contains a forbidden keyword';
    END IF;

    IF p_row_limit IS NULL OR p_row_limit < 1 OR p_row_limit > 2000 THEN
        p_row_limit := 500;
    END IF;

    PERFORM set_config('statement_timeout', '5s', true);
    EXECUTE format('SET LOCAL ROLE %I', 'ecopath_readonly');

    EXECUTE format(
        'SELECT jsonb_agg(t) FROM (SELECT * FROM (%s) AS q LIMIT %s) AS t',
        cleaned, p_row_limit
    )
    INTO result;

    RETURN COALESCE(result, '[]'::JSONB);
END;
$$;

GRANT EXECUTE ON FUNCTION dataset_coverage() TO service_role, anon, authenticated;
GRANT EXECUTE ON FUNCTION rank_states(TEXT, TEXT[], SMALLINT, SMALLINT, INTEGER)
    TO service_role, anon, authenticated;
-- Deliberately NOT granted to anon: agent-authored SQL runs only server-side.
GRANT EXECUTE ON FUNCTION exec_readonly_sql(TEXT, INTEGER) TO service_role;


-- ─── FIX: make anomaly detection genuinely idempotent ────────────────────────
-- run_anomaly_detection() inserts with `ON CONFLICT DO NOTHING`, but no unique
-- constraint existed for that clause to act on, so every run duplicated every
-- anomaly. Deduplicate what is already stored, then add the constraint the
-- insert has always assumed.

DELETE FROM anomalies a
      USING anomalies b
      WHERE a.ctid > b.ctid
        AND a.species_id   = b.species_id
        AND a.year         = b.year
        AND a.anomaly_type = b.anomaly_type;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_anomaly_species_year_type
    ON anomalies (species_id, year, anomaly_type);
