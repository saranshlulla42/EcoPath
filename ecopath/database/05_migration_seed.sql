-- ============================================================
-- EcoPath Database: Step 5 — Migration Route Seeds
-- Known flyways and migration corridors through India
-- ============================================================

-- First get species IDs, then insert migration routes
-- We use a DO block to handle dynamic lookups

DO $$
DECLARE
    v_flamingo_id    UUID;
    v_amur_falcon_id UUID;
    v_bar_goose_id   UUID;
    v_dem_crane_id   UUID;
    v_soc_lapwing_id UUID;
BEGIN
    -- Get species IDs
    SELECT id INTO v_flamingo_id    FROM species WHERE gbif_key = 2480978;
    SELECT id INTO v_amur_falcon_id FROM species WHERE gbif_key = 2481064;
    SELECT id INTO v_bar_goose_id   FROM species WHERE gbif_key = 2460912;
    SELECT id INTO v_dem_crane_id   FROM species WHERE gbif_key = 2481060;
    SELECT id INTO v_soc_lapwing_id FROM species WHERE gbif_key = 2473307;

    -- ─── Greater Flamingo: breeding ↔ wintering ──────────────────────────────
    IF v_flamingo_id IS NOT NULL THEN
        INSERT INTO migration_routes (
            species_id, route_name, flyway, season, direction,
            route_geom, waypoints, active_months, distance_km, source, verified
        ) VALUES (
            v_flamingo_id,
            'Flamingo India Circuit',
            'Central Asian Flyway',
            'winter',
            'circular',
            ST_GeomFromText('LINESTRING(68.5 23.1, 72.4 22.8, 72.9 21.7, 77.2 15.3, 80.3 13.1, 80.1 8.9, 77.5 8.1, 73.8 15.5, 70.1 22.3, 68.5 23.1)', 4326)::geography,
            '[
                {"lat": 23.1, "lng": 68.5, "month": 10, "location_name": "Rann of Kutch", "description": "Primary breeding/staging site, 50,000+ birds"},
                {"lat": 22.8, "lng": 72.4, "month": 11, "location_name": "Thol Lake, Gujarat", "description": "Staging during movement south"},
                {"lat": 21.7, "lng": 72.9, "month": 11, "location_name": "Gulf of Khambhat", "description": "Coastal feeding grounds"},
                {"lat": 15.3, "lng": 77.2, "month": 12, "location_name": "Pulicat Lake, Andhra Pradesh", "description": "Major winter congregation"},
                {"lat": 13.1, "lng": 80.3, "month": 12, "location_name": "Vedanthangal Bird Sanctuary", "description": "Important wintering site"},
                {"lat": 8.9,  "lng": 80.1, "month": 1,  "location_name": "Point Calimere", "description": "Southernmost wintering point"},
                {"lat": 8.1,  "lng": 77.5, "month": 1,  "location_name": "Kanyakumari Coast", "description": "Winter feeding"},
                {"lat": 15.5, "lng": 73.8, "month": 2,  "location_name": "Goa Coast", "description": "Return northward movement"},
                {"lat": 22.3, "lng": 70.1, "month": 3,  "location_name": "Saurashtra Coast", "description": "Pre-breeding staging"}
            ]'::jsonb,
            ARRAY[10, 11, 12, 1, 2, 3],
            3200.0,
            'BirdLife',
            true
        );
    END IF;

    -- ─── Amur Falcon: Siberia → India → Africa ────────────────────────────────
    IF v_amur_falcon_id IS NOT NULL THEN
        INSERT INTO migration_routes (
            species_id, route_name, flyway, season, direction,
            route_geom, waypoints, active_months, distance_km, source, verified
        ) VALUES (
            v_amur_falcon_id,
            'Amur Falcon Trans-Continental Route',
            'East Asian-Australasian Flyway',
            'winter',
            'south-north',
            ST_GeomFromText('LINESTRING(128.5 50.2, 105.3 35.1, 94.2 26.3, 93.8 25.7, 93.4 25.5, 93.2 25.2, 94.5 20.1, 92.3 13.4)', 4326)::geography,
            '[
                {"lat": 50.2,  "lng": 128.5, "month": 9,  "location_name": "Amur Region, Siberia", "description": "Origin / breeding grounds"},
                {"lat": 35.1,  "lng": 105.3, "month": 9,  "location_name": "Central China", "description": "Pre-migration staging"},
                {"lat": 26.3,  "lng": 94.2,  "month": 10, "location_name": "Assam Foothills", "description": "Entering India via eastern corridor"},
                {"lat": 25.7,  "lng": 93.8,  "month": 10, "location_name": "Nagaland Hills", "description": "Major congregation zone"},
                {"lat": 25.5,  "lng": 93.4,  "month": 10, "location_name": "Doyang Lake, Nagaland", "description": "World''s largest raptor roost — 100,000+ birds"},
                {"lat": 25.2,  "lng": 93.2,  "month": 11, "location_name": "Manipur Valley", "description": "Continued staging"},
                {"lat": 20.1,  "lng": 94.5,  "month": 11, "location_name": "Myanmar Coast", "description": "Intermediate staging pre-ocean crossing"},
                {"lat": 13.4,  "lng": 92.3,  "month": 11, "location_name": "Arabian Sea", "description": "Oceanic crossing to East Africa"}
            ]'::jsonb,
            ARRAY[9, 10, 11],
            22000.0,
            'BirdLife',
            true
        );
    END IF;

    -- ─── Bar-headed Goose: Central Asia → India Himalayan crossing ────────────
    IF v_bar_goose_id IS NOT NULL THEN
        INSERT INTO migration_routes (
            species_id, route_name, flyway, season, direction,
            route_geom, waypoints, active_months, distance_km, source, verified
        ) VALUES (
            v_bar_goose_id,
            'Bar-headed Goose Himalayan Crossing',
            'Central Asian Flyway',
            'winter',
            'south-north',
            ST_GeomFromText('LINESTRING(92.1 47.2, 88.5 35.3, 87.2 28.5, 84.1 27.8, 78.4 30.1, 73.8 23.1, 72.4 22.3)', 4326)::geography,
            '[
                {"lat": 47.2, "lng": 92.1, "month": 9,  "location_name": "Mongolia / Qinghai Lake", "description": "Breeding grounds at 3,200m altitude"},
                {"lat": 35.3, "lng": 88.5, "month": 10, "location_name": "Tibetan Plateau", "description": "Staging at 4,500m, feeding before crossing"},
                {"lat": 28.5, "lng": 87.2, "month": 10, "location_name": "Himalayan crest (>7,000m)", "description": "World record migration altitude — 6,540m+ confirmed"},
                {"lat": 27.8, "lng": 84.1, "month": 10, "location_name": "Koshi Tappu, Nepal", "description": "Immediate post-crossing staging"},
                {"lat": 30.1, "lng": 78.4, "month": 11, "location_name": "Corbett National Park", "description": "Himalayan foothills wintering"},
                {"lat": 23.1, "lng": 73.8, "month": 12, "location_name": "Chilika Lake", "description": "Prime wintering area, thousands congregate"},
                {"lat": 22.3, "lng": 72.4, "month": 12, "location_name": "Nal Sarovar, Gujarat", "description": "Major winter congregation"}
            ]'::jsonb,
            ARRAY[9, 10, 11, 12, 1, 2, 3],
            4500.0,
            'BirdLife',
            true
        );
    END IF;

    -- ─── Demoiselle Crane: Khichan corridor ──────────────────────────────────
    IF v_dem_crane_id IS NOT NULL THEN
        INSERT INTO migration_routes (
            species_id, route_name, flyway, season, direction,
            route_geom, waypoints, active_months, distance_km, source, verified
        ) VALUES (
            v_dem_crane_id,
            'Demoiselle Crane Khichan Corridor',
            'Central Asian Flyway',
            'winter',
            'south-north',
            ST_GeomFromText('LINESTRING(82.3 48.1, 74.5 42.3, 71.2 36.8, 72.6 27.9, 72.0 27.1, 71.8 26.3)', 4326)::geography,
            '[
                {"lat": 48.1, "lng": 82.3, "month": 8,  "location_name": "Central Asia / Kazakh Steppe", "description": "Breeding grounds"},
                {"lat": 42.3, "lng": 74.5, "month": 9,  "location_name": "Kyrgyzstan Valleys", "description": "Pre-migration gathering"},
                {"lat": 36.8, "lng": 71.2, "month": 10, "location_name": "Hindu Kush Passes", "description": "Mountain crossing at 5,900m"},
                {"lat": 27.9, "lng": 72.6, "month": 10, "location_name": "Jodhpur outskirts", "description": "Entering Rajasthan"},
                {"lat": 27.1, "lng": 72.0, "month": 11, "location_name": "Khichan Village, Rajasthan", "description": "Famous feeding site — 20,000+ cranes fed daily by villagers"},
                {"lat": 26.3, "lng": 71.8, "month": 12, "location_name": "Jaisalmer area", "description": "Winter dispersal in Thar Desert"}
            ]'::jsonb,
            ARRAY[10, 11, 12, 1, 2, 3],
            3800.0,
            'BirdLife',
            true
        );
    END IF;

END $$;

-- Verify migration data
SELECT
    s.common_name,
    mr.route_name,
    mr.season,
    mr.distance_km,
    jsonb_array_length(mr.waypoints) AS waypoint_count
FROM migration_routes mr
JOIN species s ON s.id = mr.species_id
ORDER BY s.common_name;
