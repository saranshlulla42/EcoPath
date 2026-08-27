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
        "description": "Fetches detected anomaly events — population surges, dips, local extinctions, and recolonizations — for a species. Each anomaly includes its Z-score, severity, and weather context. Use this when the user asks about unusual changes, sudden drops, unexpected spikes, disappearances, or anything about what went wrong or what happened to a species.",
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

agent_tools = [
    query_population_func,
    query_anomalies_func,
    query_migration_func,
    compare_species_func,
    correlate_weather_func,
]
