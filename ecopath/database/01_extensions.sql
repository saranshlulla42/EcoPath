-- ============================================================
-- EcoPath Database: Step 1 — Enable Extensions
-- Run this first in the Supabase SQL Editor
-- ============================================================

-- Enable PostGIS for geospatial operations (points, polygons, linestrings)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable PostGIS topology for advanced spatial analysis
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Enable fuzzy string matching for species name search
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Verify extensions are active
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name IN ('postgis', 'pg_trgm', 'uuid-ossp')
ORDER BY name;
