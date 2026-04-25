-- ============================================================
-- EcoPath Database: Step 4 — Analytical Functions
-- Rolling average computation + anomaly detection engine
-- ============================================================

-- ─── FUNCTION: Get yearly observation totals for a species ───────────────────
CREATE OR REPLACE FUNCTION get_yearly_totals(p_species_id UUID)
RETURNS TABLE (
    year        SMALLINT,
    total_count BIGINT,
    state_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        pr.year,
        SUM(pr.observation_count)::BIGINT AS total_count,
        COUNT(DISTINCT pr.state_name)::BIGINT AS state_count
    FROM population_records pr
    WHERE pr.species_id = p_species_id
    GROUP BY pr.year
    ORDER BY pr.year;
END;
$$ LANGUAGE plpgsql STABLE;


-- ─── FUNCTION: Compute 5-year rolling average ────────────────────────────────
CREATE OR REPLACE FUNCTION compute_rolling_avg_5yr(p_species_id UUID, p_year SMALLINT)
RETURNS NUMERIC AS $$
DECLARE
    v_avg NUMERIC;
BEGIN
    SELECT AVG(yearly.total)
    INTO v_avg
    FROM (
        SELECT SUM(observation_count) AS total
        FROM population_records
        WHERE species_id = p_species_id
          AND year BETWEEN (p_year - 5) AND (p_year - 1)
        GROUP BY year
    ) yearly;

    RETURN COALESCE(v_avg, 0);
END;
$$ LANGUAGE plpgsql STABLE;


-- ─── FUNCTION: Detect anomalies for a single species + year ─────────────────
-- Uses >1.5 standard deviations from 5-year rolling average + std dev
CREATE OR REPLACE FUNCTION detect_anomaly_for_year(
    p_species_id UUID,
    p_year       SMALLINT
)
RETURNS TABLE (
    anomaly_type     TEXT,
    magnitude_pct    NUMERIC,
    severity         TEXT,
    observed_count   INTEGER,
    expected_count   INTEGER,
    rolling_avg_5yr  NUMERIC
) AS $$
DECLARE
    v_observed   BIGINT;
    v_rolling    NUMERIC;
    v_stddev     NUMERIC;
    v_z_score    NUMERIC;
    v_magnitude  NUMERIC;
    v_type       TEXT;
    v_severity   TEXT;
BEGIN
    -- Get observed count for this year
    SELECT SUM(observation_count)
    INTO v_observed
    FROM population_records
    WHERE species_id = p_species_id AND year = p_year;

    -- Must have data for this year
    IF v_observed IS NULL THEN
        RETURN;
    END IF;

    -- Get 5-year rolling average and std dev (requires data from at least 2 prior years)
    SELECT AVG(yearly.total), COALESCE(STDDEV_POP(yearly.total), 0)
    INTO v_rolling, v_stddev
    FROM (
        SELECT SUM(observation_count) AS total
        FROM population_records
        WHERE species_id = p_species_id
          AND year BETWEEN (p_year - 5) AND (p_year - 1)
        GROUP BY year
    ) yearly;

    v_rolling := COALESCE(v_rolling, 0);

    -- Cannot detect anomaly without baseline
    IF v_rolling = 0 THEN
        RETURN;
    END IF;

    -- Compute % deviation
    v_magnitude := ((v_observed - v_rolling) / v_rolling) * 100;

    -- Compute z-score; if stddev is 0 fall back to % threshold
    IF v_stddev > 0 THEN
        v_z_score := ABS(v_observed - v_rolling) / v_stddev;
        -- Apply >1.5 standard deviation threshold
        IF v_z_score < 1.5 THEN
            RETURN;  -- No anomaly
        END IF;
    ELSE
        -- No variance in historical data: flag if >25% deviation
        IF ABS(v_magnitude) < 25 THEN
            RETURN;
        END IF;
    END IF;

    -- Classify type
    IF v_magnitude > 0 THEN
        v_type := 'surge';
    ELSIF v_observed = 0 THEN
        v_type := 'local_extinction';
    ELSE
        v_type := 'dip';
    END IF;

    -- Classify severity based on z-score (or magnitude if no stddev)
    IF v_stddev > 0 THEN
        IF v_z_score >= 3.0 THEN
            v_severity := 'critical';
        ELSIF v_z_score >= 2.5 THEN
            v_severity := 'high';
        ELSIF v_z_score >= 2.0 THEN
            v_severity := 'medium';
        ELSE
            v_severity := 'low';
        END IF;
    ELSE
        IF ABS(v_magnitude) >= 75 THEN
            v_severity := 'critical';
        ELSIF ABS(v_magnitude) >= 50 THEN
            v_severity := 'high';
        ELSIF ABS(v_magnitude) >= 35 THEN
            v_severity := 'medium';
        ELSE
            v_severity := 'low';
        END IF;
    END IF;

    RETURN QUERY SELECT
        v_type,
        ROUND(v_magnitude, 2),
        v_severity,
        v_observed::INTEGER,
        ROUND(v_rolling)::INTEGER,
        ROUND(v_rolling, 2);
END;
$$ LANGUAGE plpgsql STABLE;


-- ─── FUNCTION: Run full anomaly detection for all species ────────────────────
-- Call this after each ingestion batch
CREATE OR REPLACE FUNCTION run_anomaly_detection(p_start_year SMALLINT DEFAULT 2020)
RETURNS TABLE (
    species_id   UUID,
    species_name TEXT,
    year         SMALLINT,
    anomaly_type TEXT,
    severity     TEXT,
    magnitude    NUMERIC
) AS $$
DECLARE
    r_species RECORD;
    r_year    SMALLINT;
    r_anomaly RECORD;
BEGIN
    FOR r_species IN
        SELECT DISTINCT s.id, s.common_name
        FROM species s
        JOIN population_records pr ON pr.species_id = s.id
        ORDER BY s.common_name
    LOOP
        FOR r_year IN
            SELECT DISTINCT pr.year
            FROM population_records pr
            WHERE pr.species_id = r_species.id
              AND pr.year >= p_start_year
            ORDER BY pr.year
        LOOP
            FOR r_anomaly IN
                SELECT * FROM detect_anomaly_for_year(r_species.id, r_year)
            LOOP
                -- Upsert into anomalies table
                INSERT INTO anomalies (
                    species_id, year, anomaly_type, magnitude_pct,
                    severity, observed_count, expected_count, rolling_avg_5yr
                )
                VALUES (
                    r_species.id, r_year, r_anomaly.anomaly_type, r_anomaly.magnitude_pct,
                    r_anomaly.severity, r_anomaly.observed_count,
                    r_anomaly.expected_count, r_anomaly.rolling_avg_5yr
                )
                ON CONFLICT DO NOTHING;

                -- Return summary
                RETURN QUERY SELECT
                    r_species.id,
                    r_species.common_name,
                    r_year,
                    r_anomaly.anomaly_type,
                    r_anomaly.severity,
                    r_anomaly.magnitude_pct;
            END LOOP;
        END LOOP;
    END LOOP;
END;
$$ LANGUAGE plpgsql;


-- ─── VIEW: Population trend summary (for dashboard charts) ───────────────────
CREATE OR REPLACE VIEW v_population_trends AS
SELECT
    s.id AS species_id,
    s.common_name,
    s.scientific_name,
    s.iucn_status,
    pr.year,
    SUM(pr.observation_count) AS total_observations,
    COUNT(DISTINCT pr.state_name) AS states_observed,
    COUNT(DISTINCT pr.district) AS districts_observed,
    AVG(pr.observation_count) AS avg_obs_per_site
FROM species s
JOIN population_records pr ON pr.species_id = s.id
GROUP BY s.id, s.common_name, s.scientific_name, s.iucn_status, pr.year
ORDER BY s.common_name, pr.year;


-- ─── VIEW: Active anomalies with species context ─────────────────────────────
CREATE OR REPLACE VIEW v_active_anomalies AS
SELECT
    a.id,
    s.common_name,
    s.scientific_name,
    s.iucn_status,
    a.year,
    a.anomaly_type,
    a.severity,
    a.magnitude_pct,
    a.affected_state,
    a.observed_count,
    a.expected_count,
    a.causal_hypothesis,
    a.detected_at
FROM anomalies a
JOIN species s ON s.id = a.species_id
WHERE a.reviewed = false
ORDER BY
    CASE a.severity
        WHEN 'critical' THEN 1
        WHEN 'high' THEN 2
        WHEN 'medium' THEN 3
        ELSE 4
    END,
    a.detected_at DESC;


-- ─── FUNCTION: Heatmap GeoJSON for a species + year ─────────────────────────
CREATE OR REPLACE FUNCTION get_heatmap_geojson(p_species_id UUID, p_year SMALLINT)
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'type', 'FeatureCollection',
        'features', COALESCE(jsonb_agg(
            jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(location)::jsonb,
                'properties', jsonb_build_object(
                    'count', observation_count,
                    'state', state_name,
                    'district', district,
                    'year', year
                )
            )
        ), '[]'::jsonb)
    )
    INTO result
    FROM population_records
    WHERE species_id = p_species_id
      AND year = p_year
      AND location IS NOT NULL;

    RETURN result;
END;
$$ LANGUAGE plpgsql STABLE;
