query_population_func = {
    "type": "function",
    "function": {
        "name": "query_population",
        "description": "Fetches bird observation count data over time for a species, optionally filtered by region and year range. Use this when the user asks about population trends, numbers, counts, observation data, how a species is doing in a region, whether numbers are going up or down, or any question that needs quantitative time-series data.",
        "parameters": {
            "type": "object",
            "properties": {
                "species_name": {
                    "type": "string",
                    "description": "Common name or scientific name of the bird species"
                },
                "regions": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "State codes (e.g. 'GJ', 'RJ') or country codes (e.g. 'IN'). Omit for all regions."
                },
                "year_start": {
                    "type": "integer",
                    "description": "Start year. Default 2014."
                },
                "year_end": {
                    "type": "integer",
                    "description": "End year. Default 2024."
                }
            },
            "required": ["species_name"]
        }
    }
}

query_anomalies_func = {
    "type": "function",
    "function": {
        "name": "query_anomalies",
        "description": "Fetches detected anomaly events — population surges, dips, local extinctions, and recolonizations — for a species. Each anomaly includes its percentage deviation from the 5-year rolling average, severity, confidence score, and weather context. Use this when the user asks about unusual changes, sudden drops, unexpected spikes, disappearances, or anything about what went wrong or what happened to a species.",
        "parameters": {
            "type": "object",
            "properties": {
                "species_name": {
                    "type": "string",
                    "description": "Common name or scientific name of the bird species"
                },
                "region": {
                    "type": "string",
                    "description": "A single state code (e.g. 'GJ') or country code (e.g. 'IN')"
                },
                "severity_min": {
                    "type": "string",
                    "description": "Minimum severity to include. One of: 'low', 'medium', 'high', 'critical'. Default: 'low'"
                },
                "year": {
                    "type": "integer",
                    "description": "Filter to a specific year. If omitted, return all years."
                }
            },
            "required": ["species_name"]
        }
    }
}

query_migration_func = {
    "type": "function",
    "function": {
        "name": "query_migration",
        "description": "Fetches migration route data for a species including GeoJSON flight paths, stopover locations, seasons, and distances. Use this when the user asks about where a bird migrates, its flyway, migration route, seasonal movement, or stopover sites. Also use this to check whether a species is migratory or resident.",
        "parameters": {
            "type": "object",
            "properties": {
                "species_name": {
                    "type": "string",
                    "description": "Common name or scientific name of the bird species"
                },
                "season": {
                    "type": "string",
                    "description": "'spring', 'autumn', or 'both'. Default: 'both'."
                }
            },
            "required": ["species_name"]
        }
    }
}

compare_species_func = {
    "type": "function",
    "function": {
        "name": "compare_species",
        "description": "Fetches parallel population data and ecological profiles for two species side by side. Use this when the user asks to compare two birds, see which is doing better, or understand differences between species in the same region.",
        "parameters": {
            "type": "object",
            "properties": {
                "species_a": {
                    "type": "string",
                    "description": "First species name"
                },
                "species_b": {
                    "type": "string",
                    "description": "Second species name"
                },
                "regions": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Regions to compare in. Default: all India."
                },
                "year_start": {
                    "type": "integer",
                    "description": "Default: 2014"
                },
                "year_end": {
                    "type": "integer",
                    "description": "Default: 2024"
                }
            },
            "required": ["species_a", "species_b"]
        }
    }
}

correlate_weather_func = {
    "type": "function",
    "function": {
        "name": "correlate_weather",
        "description": "Fetches population data AND historical weather data (temperature, rainfall, extreme heat days) for a species in a specific region, aligned by year. Use this when the user asks about climate impact, weather effects on populations, why a population changed during a particular period, or any question linking bird numbers to environmental conditions.",
        "parameters": {
            "type": "object",
            "properties": {
                "species_name": {
                    "type": "string",
                    "description": "Common name or scientific name of the bird species"
                },
                "region": {
                    "type": "string",
                    "description": "A single state code. Required."
                },
                "year_start": {
                    "type": "integer",
                    "description": "Default: 2014"
                },
                "year_end": {
                    "type": "integer",
                    "description": "Default: 2024"
                }
            },
            "required": ["species_name", "region"]
        }
    }
}


describe_dataset_func = {
    "type": "function",
    "function": {
        "name": "describe_dataset",
        "description": (
            "Reports what EcoPath's database actually contains: how many species are catalogued, "
            "how many have observation records, the year span covered, which states appear, the "
            "IUCN breakdown, and which tables are empty. Call this FIRST whenever another tool "
            "returns no data, before you explain the absence — so you can state the real coverage "
            "gap instead of speculating about ecology. Also useful when the user asks what data "
            "you have, what you can answer, or how complete the dataset is."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}

list_species_func = {
    "type": "function",
    "function": {
        "name": "list_species",
        "description": (
            "Finds species matching conservation status, region, family, migratory behaviour or a "
            "name fragment. Use this for any question that asks WHICH birds rather than about one "
            "named bird — 'which endangered species live in Assam', 'list the critically "
            "endangered raptors', 'what migratory birds does EcoPath track'. Also use it to "
            "resolve a vague species reference into concrete names before calling another tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "iucn_status": {
                    "type": "string",
                    "description": (
                        "IUCN code (LC, NT, VU, EN, CR) or a plain word: 'threatened' (VU+EN+CR), "
                        "'endangered' (EN+CR), 'critically endangered', 'vulnerable'."
                    ),
                },
                "region": {
                    "type": "string",
                    "description": "State code (e.g. 'GJ') or state name. Omit for all India.",
                },
                "migratory": {"type": "boolean", "description": "Filter to migratory or resident species."},
                "family": {"type": "string", "description": "Taxonomic family, e.g. 'Accipitridae'."},
                "name_contains": {"type": "string", "description": "Substring of the common or scientific name."},
                "with_records_only": {
                    "type": "boolean",
                    "description": "Only return species EcoPath holds observation data for. Default false.",
                },
                "limit": {"type": "integer", "description": "Max species to return. Default 50, max 200."},
            },
        },
    },
}

rank_regions_func = {
    "type": "function",
    "function": {
        "name": "rank_regions",
        "description": (
            "Ranks Indian states against each other on a metric computed across the whole species "
            "catalogue. Use this for superlative and comparison questions about places — 'which "
            "state has the most endangered birds', 'where are observations concentrated', 'rank "
            "states by species richness'. This is the only tool that aggregates across species; "
            "the population tools all need one named species."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "description": (
                        "'species_richness' (distinct species recorded, the default), "
                        "'threatened_species' (distinct VU/EN/CR species), or "
                        "'observations' (total observation count)."
                    ),
                },
                "iucn_status": {
                    "type": "string",
                    "description": "Restrict the ranking to a status or status group, e.g. 'CR' or 'threatened'.",
                },
                "year_start": {"type": "integer", "description": "Optional start year."},
                "year_end": {"type": "integer", "description": "Optional end year."},
                "limit": {"type": "integer", "description": "How many states to return. Default 15, max 40."},
            },
        },
    },
}

run_sql_func = {
    "type": "function",
    "function": {
        "name": "run_sql",
        "description": (
            "Runs one read-only SQL SELECT against EcoPath's database. You will be shown at most "
            "50 rows regardless of what you ask for, so aggregate in SQL (COUNT, SUM, AVG, GROUP BY) "
            "rather than selecting raw rows and counting them yourself. Use "
            "this ONLY when no other tool can express the question — multi-way aggregations, "
            "correlations across tables, arbitrary groupings, 'top N by X per Y'. Prefer the typed "
            "tools when one fits; they return richer context.\n\n"
            "Schema (PostgreSQL):\n"
            "  species(id uuid, gbif_key int, common_name text, scientific_name text, family text,\n"
            "          order_name text, class_name text, iucn_status text CHECK IN\n"
            "          ('LC','NT','VU','EN','CR','EW','EX','DD','NE'), endemic_india bool,\n"
            "          migratory bool, primary_habitat text[], primary_range text[], description text,\n"
            "          fun_fact text)\n"
            "  population_records(id uuid, species_id uuid -> species.id, year smallint,\n"
            "          month smallint, observation_count int, state_name text, district text,\n"
            "          data_source text)\n"
            "  anomalies(id uuid, species_id uuid -> species.id, year smallint, anomaly_type text\n"
            "          CHECK IN ('surge','dip','local_extinction','recolonization'), magnitude_pct numeric,\n"
            "          severity text CHECK IN ('low','medium','high','critical'), affected_state text,\n"
            "          observed_count int, expected_count int, rolling_avg_5yr numeric,\n"
            "          causal_hypothesis text, weather_context jsonb, confidence_score numeric)\n"
            "  migration_routes(id uuid, species_id uuid -> species.id, route_name text, flyway text,\n"
            "          season text CHECK IN ('winter','summer','monsoon','post-monsoon','year-round'),\n"
            "          direction text, waypoints jsonb, active_months int[], distance_km numeric)\n\n"
            "Rules: exactly one statement, SELECT or WITH only, no semicolons, no DDL or DML. "
            "At most 50 rows reach you; the result says how many were withheld. state_name holds "
            "full names ('Tamil Nadu'), not codes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single SELECT or WITH statement."},
                "row_limit": {"type": "integer", "description": "Max rows the query may match. Default 200. At most 50 are shown to you."},
            },
            "required": ["query"],
        },
    },
}

agent_tools = [
    query_population_func,
    query_anomalies_func,
    query_migration_func,
    compare_species_func,
    correlate_weather_func,
    describe_dataset_func,
    list_species_func,
    rank_regions_func,
    run_sql_func,
]
