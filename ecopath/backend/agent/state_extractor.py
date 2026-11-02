"""
Post-turn session state extraction.

After every completed agent turn we work out what the user is now researching,
so the next turn's system prompt can resolve "it", "there" and "that period".
Tool call arguments are the primary signal; a lightweight scan of the user's
message is the fallback for turns where no tool fired.
"""

import logging
import re
import time
from typing import Optional

from agent.session import ResearchSession, ToolCallRecord, TurnData
from agent.tools import CODE_TO_STATE

logger = logging.getLogger("ecopath.agent.state_extractor")

MAX_KEY_FINDINGS = 5
MAX_FINDING_CHARS = 150

TREND_WORDS = (
    "decline", "increase", "surge", "drop", "rise", "extinction",
    "critical", "anomaly", "peak", "lowest", "highest", "correlation",
)

# Argument names each tool uses for the species / region / year fields.
SPECIES_ARG_KEYS = ("species_name", "species_a", "species_b", "species")
REGION_ARG_KEYS = ("regions", "region")


# ─── Key findings ─────────────────────────────────────────────────────────────

def extract_key_findings(blocks: list[dict]) -> list[str]:
    """
    Pull sentences carrying concrete data points out of the narrative blocks.
    Deliberately crude — the raw history still holds the real numbers for recent
    turns, this only needs to be good enough to jog the model's memory.
    """
    findings: list[str] = []
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "narrative":
            continue
        content = block.get("content") or ""
        for sentence in content.split(". "):
            has_number = any(char.isdigit() for char in sentence)
            if not has_number:
                continue
            lowered = sentence.lower()
            if "%" not in sentence and not any(w in lowered for w in TREND_WORDS):
                continue
            finding = " ".join(sentence.split()).strip().rstrip(".")
            if not finding:
                continue
            if len(finding) > MAX_FINDING_CHARS:
                finding = finding[: MAX_FINDING_CHARS - 3] + "..."
            if finding not in findings:
                findings.append(finding)

    return findings[:MAX_KEY_FINDINGS]


# ─── Species name cache (for entity extraction) ───────────────────────────────

_species_cache: list[dict] = []
_species_cache_loaded_at: float = 0.0
_SPECIES_CACHE_TTL = 60 * 60  # 1 hour


def get_cached_species_list() -> list[dict]:
    """
    All species names from Supabase, cached. Failures are soft: entity extraction
    is only a fallback, so an empty list degrades gracefully rather than breaking
    the turn.
    """
    global _species_cache, _species_cache_loaded_at

    if _species_cache and (time.time() - _species_cache_loaded_at) < _SPECIES_CACHE_TTL:
        return _species_cache

    try:
        # Read through the data layer, which pages. A plain select stops at
        # PostgREST's 1000-row default, which silently hid 413 of the 1413
        # catalogued species from entity extraction.
        from data import repository as repo

        result = repo.species_catalogue("common_name,scientific_name")
        _species_cache = [s for s in (result.data or []) if s.get("common_name")]
        _species_cache_loaded_at = time.time()
        logger.info(f"Cached {len(_species_cache)} species names for entity extraction.")
    except Exception as e:
        logger.warning(f"Could not load species list for entity extraction: {e}")
        _species_cache_loaded_at = time.time()  # don't hammer a broken connection

    return _species_cache


def clear_species_cache() -> None:
    global _species_cache, _species_cache_loaded_at
    _species_cache = []
    _species_cache_loaded_at = 0.0


def extract_entities_from_message(message: str, species_list: Optional[list[dict]] = None) -> dict:
    """
    Quick scan of the user's message for a known species name and state
    references. Only used to update session state when a turn fired no tools.
    """
    entities: dict = {"species": None, "regions": []}
    if not message:
        return entities

    message_lower = message.lower()
    if species_list is None:
        species_list = get_cached_species_list()

    # Longest name first, so "White-rumped Vulture" beats a bare "Vulture" entry.
    for species in sorted(
        species_list, key=lambda s: len(s.get("common_name") or ""), reverse=True
    ):
        common = (species.get("common_name") or "").lower()
        scientific = (species.get("scientific_name") or "").lower()
        if common and common in message_lower:
            entities["species"] = species["common_name"]
            break
        if scientific and scientific in message_lower:
            entities["species"] = species["common_name"]
            break

    for code, name in CODE_TO_STATE.items():
        # State names match case-insensitively on a word boundary; bare codes only
        # match as standalone uppercase tokens, so "as" never becomes Assam.
        if re.search(rf"\b{re.escape(name)}\b", message, flags=re.IGNORECASE) or re.search(
            rf"\b{code}\b", message
        ):
            if code not in entities["regions"]:
                entities["regions"].append(code)

    return entities


# ─── Session state update ─────────────────────────────────────────────────────

def _record_species(session: ResearchSession, name: Optional[str], scientific: Optional[str] = None):
    if not name:
        return
    changed = session.active_species != name
    session.active_species = name
    # Only tools that return population data carry the scientific name. A later
    # call for the same species must not blank out what an earlier one resolved.
    if scientific or changed:
        session.active_species_scientific = scientific
    if name not in session.all_species_discussed:
        session.all_species_discussed.append(name)


def _record_regions(session: ResearchSession, regions: list[str]):
    if not regions:
        return
    session.active_regions = regions
    for r in regions:
        if r not in session.all_regions_discussed:
            session.all_regions_discussed.append(r)


def _species_from_call(call: ToolCallRecord) -> tuple[Optional[str], Optional[str]]:
    """
    Best available species identity for a tool call: prefer the canonical name the
    tool resolved to, fall back to what the model asked for.
    """
    result = call.result if isinstance(call.result, dict) else {}

    if isinstance(result.get("species_a"), dict):  # compare_species shape
        a = result["species_a"]
        return a.get("name"), a.get("scientific_name")

    if result.get("species") and not result.get("error"):
        return result["species"], result.get("scientific_name")

    for key in SPECIES_ARG_KEYS:
        value = call.args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), None

    return None, None


def _regions_from_call(call: ToolCallRecord) -> list[str]:
    for key in REGION_ARG_KEYS:
        value = call.args.get(key)
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        if isinstance(value, (list, tuple)):
            regions = [str(v).strip() for v in value if str(v).strip()]
            if regions:
                return regions
    return []


def update_session_state(session: ResearchSession, turn_data: TurnData) -> None:
    """
    Fold one completed turn into the session state. Called after the agent's final
    response is parsed and before it is streamed to the frontend.
    """
    session.touch()
    session.turn_count += 1

    for call in turn_data.tool_calls:
        name, scientific = _species_from_call(call)
        _record_species(session, name, scientific)

        # compare_species touches two species; the second one still belongs in the
        # session's running list even though the first stays "active".
        result = call.result if isinstance(call.result, dict) else {}
        if isinstance(result.get("species_b"), dict):
            partner = result["species_b"].get("name")
            if partner and partner not in session.all_species_discussed:
                session.all_species_discussed.append(partner)
        elif call.args.get("species_b"):
            partner = str(call.args["species_b"]).strip()
            if partner and partner not in session.all_species_discussed:
                session.all_species_discussed.append(partner)

        _record_regions(session, _regions_from_call(call))

        year_start = call.args.get("year_start")
        year_end = call.args.get("year_end")
        if year_start or year_end:
            session.active_year_range = (
                int(year_start) if year_start else session.active_year_range[0],
                int(year_end) if year_end else session.active_year_range[1],
            )

    # No tools fired — fall back to reading the user's message directly, so a
    # knowledge-only answer about a new species still moves the focus.
    if not turn_data.tool_calls:
        entities = extract_entities_from_message(turn_data.user_message)
        if entities["species"]:
            _record_species(session, entities["species"])
        _record_regions(session, entities["regions"])

    session.last_tool_calls = [call.name for call in turn_data.tool_calls]
    session.last_visualization_types = [
        block["type"]
        for block in turn_data.final_blocks
        if isinstance(block, dict)
        and block.get("type") not in ("narrative", "follow_ups")
        and block.get("type")
    ]
    session.last_key_findings = extract_key_findings(turn_data.final_blocks)
