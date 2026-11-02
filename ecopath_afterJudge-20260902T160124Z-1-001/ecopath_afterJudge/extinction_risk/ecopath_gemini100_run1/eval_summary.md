# EcoPath Model Evaluation Report

## Summary Statistics

| Metric | Base Model (Qwen2.5-7B) | Fine-Tuned (EcoPath) | Delta |
|--------|---------|---------|-------|
| JSON Validity (%) | 0.0 | 100.0 | +100.0 |
| Schema Compliance (%) | 0.0 | 100.0 | +100.0 |
| IUCN Status Accuracy (%) | N/A | N/A | — |
| Judge: Format (avg/5) | N/A | N/A | — |
| Judge: Factual Accuracy (avg/5) | N/A | N/A | — |
| Judge: Completeness (avg/5) | N/A | N/A | — |
| Judge: Usefulness (avg/5) | N/A | N/A | — |

> **n (base)** = 15 &emsp; **n (fine-tuned)** = 15

## Per-Species Results

| # | Species | Base JSON? | FT JSON? | Base Schema? | FT Schema? | IUCN GT | Base Status | FT Status |
|---|---------|-----------|---------|-------------|-----------|---------|------------|----------|
| 1 | Herring Gull | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Herring Gull).'} |
| 2 | Mediterranean Gull | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Mediterranean Gull).'} |
| 3 | European Goldfinch | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: European Goldfinch).'} |
| 4 | Eurasian Hobby | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Eurasian Hobby).'} |
| 5 | Eurasian Hoopoe | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Eurasian Hoopoe).'} |
| 6 | Common Murre | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Common Murre).'} |
| 7 | Southern Cassowary | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Southern Cassowary).'} |
| 8 | Crested Lark | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Crested Lark).'} |
| 9 | Tawny Owl | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Tawny Owl).'} |
| 10 | Song Thrush | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Song Thrush).'} |
| 11 | Common House-Martin | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Common House-Martin).'} |
| 12 | Peregrine Falcon | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Peregrine Falcon).'} |
| 13 | European Turtle-Dove | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': "The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile. Heuristic analysis flags an 'elevating' risk direction with 'evidence_indicates_localized_or_regional_pressure', but specific threat details are not documented in the provided evidence."} |
| 14 | Eurasian Collared-Dove | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current global IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Eurasian Collared-Dove).'} |
| 15 | Barn Swallow | NO | YES | FAIL | OK | — | — | {'iucn_status': 'Unavailable', 'population_trend': 'Unavailable', 'population_size': 'Unavailable', 'status_summary': 'The current IUCN Red List status, population size, and population trend are unavailable in the provided species profile (GBIF species profile: Barn Swallow).'} |

## Interpretation

- **JSON Validity**: fraction of outputs that could be parsed as JSON.
- **Schema Compliance**: parsed JSON also contains all required keys.
- **IUCN Accuracy**: extracted `current_conservation_status` matches the IUCN ground-truth label.
- **Judge scores** are rated 1–5 by Gemini on format, factuality, completeness, and usefulness.

> Generated by `grade_results.py`.