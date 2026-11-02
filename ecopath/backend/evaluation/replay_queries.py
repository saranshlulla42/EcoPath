"""Representative queries for token measurement replay.

Chosen to spread across the declared tools and across conversation shapes, and
to name species/states that actually exist in the database, so results reflect
real work rather than "no such species" short-circuits.

Multi-turn scenarios share one session, so history accumulates exactly as it
does in real use — that is what makes `resend_multiplier` and the `history`
stage meaningful. Single-turn scenarios each get a fresh session, so their
round-0 prompt measures the true fixed floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Scenario:
    name: str
    turns: list[str]
    # What this scenario is meant to exercise, for reading the report.
    intent: str = ""
    tags: list[str] = field(default_factory=list)


SCENARIOS: list[Scenario] = [
    # ── single-turn: one per tool family, fresh session each ──────────────
    Scenario(
        "catalog_threatened",
        ["Which bird species in the dataset are critically endangered?"],
        "list_species with an IUCN filter; small result, big fixed prefix",
        ["list_species"],
    ),
    Scenario(
        "dataset_overview",
        ["What data do you actually have — how many species, which years, which states?"],
        "describe_dataset; the coverage path",
        ["describe_dataset"],
    ),
    Scenario(
        "population_trend",
        ["How have Sarus Crane numbers changed over time?"],
        "query_population, single species, full year range",
        ["query_population"],
    ),
    Scenario(
        "population_windowed",
        ["Show me population trends for the Great Indian Bustard between 2015 and 2024."],
        "query_population with an explicit window",
        ["query_population"],
    ),
    Scenario(
        "anomaly_region",
        ["Are there any unusual population drops in Kerala?"],
        "query_anomalies; anomalies table is well populated (~7.5k rows)",
        ["query_anomalies"],
    ),
    Scenario(
        "regional_ranking",
        ["Which states have the most bird observations?"],
        "rank_regions -> rank_states RPC",
        ["rank_regions"],
    ),
    Scenario(
        "species_comparison",
        ["Compare the Greater Flamingo and the Lesser Flamingo."],
        "compare_species; two-series result, larger tool payload",
        ["compare_species"],
    ),
    Scenario(
        "weather_correlation",
        ["Does rainfall affect Bar-headed Goose numbers in Gujarat?"],
        "correlate_weather; external service in the loop",
        ["correlate_weather"],
    ),
    Scenario(
        "migration_routes",
        ["What migration routes do you have for the Amur Falcon?"],
        "query_migration; only 4 routes stored, so expect a sparse answer",
        ["query_migration"],
    ),
    Scenario(
        "adhoc_sql",
        ["How many species are there in each IUCN category, counting only ones with population records?"],
        "run_sql escape hatch; the suspected fat-result path",
        ["run_sql"],
    ),
    Scenario(
        "coverage_caveat",
        ["Is the Forest Owlet actually rare, or do you just not have much data on it?"],
        "forces the data-coverage distinction; usually multi-tool",
        ["multi_tool"],
    ),
    # ── multi-turn: history growth and pronoun resolution ─────────────────
    Scenario(
        "followup_species",
        [
            "How is the Great Indian Bustard doing?",
            "Where is it found?",
            "Compare that with the Bengal Florican.",
        ],
        "pronoun resolution across turns; history and session-context growth",
        ["multi_turn"],
    ),
    Scenario(
        "followup_region",
        [
            "Show me anomalies in Assam.",
            "What about Kerala?",
            "Which species drove those?",
        ],
        "region switching; repeated tool calls accumulate tool results",
        ["multi_turn"],
    ),
    Scenario(
        "followup_drilldown",
        [
            "Which states have the most threatened species?",
            "Focus on Gujarat.",
            "Show me the trend there since 2018.",
        ],
        "progressive narrowing; deepest history of the set",
        ["multi_turn"],
    ),
]


def total_turns() -> int:
    return sum(len(s.turns) for s in SCENARIOS)


def by_name(name: str) -> Scenario | None:
    return next((s for s in SCENARIOS if s.name == name), None)
