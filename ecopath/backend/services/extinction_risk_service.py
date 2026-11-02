"""
EcoPath — Extinction Risk Report Service

Retrieves species context, gathers species-scoped threat evidence, and calls a
local Ollama-hosted instruction model to draft a reviewer-facing decision-support
report.

This mirrors the existing Gemini service pattern, but keeps the final synthesis
local so the feature can run on localhost without external paid inference.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx
from fastapi import HTTPException

from config import get_settings
from data import repository as repo
from data.sources import evidence as evidence_source
from data.sources import gbif as gbif_source
from data.sources import ollama as ollama_source


logger = logging.getLogger("ecopath.extinction_risk")
settings = get_settings()


GBIF_BASE = settings.gbif_base_url
# GDELT and news throttling, cooldowns and caching now live in the shared data
# layer (see data/registry.py and data/cache.py), so the private globals that
# used to coordinate them here have been removed.

_THREAT_QUERY_TEMPLATES = [
    "habitat loss deforestation land-use change",
    "climate change drought heat stress rainfall variability",
    "wetland drainage agriculture urban expansion",
    "poaching hunting disturbance trade",
    "policy conservation protected area development",
    "population decline endangered birds",
]

_IUCN_STATUS_ALIASES: dict[str, str] = {
    "lc": "LC",
    "least concern": "LC",
    "nt": "NT",
    "near threatened": "NT",
    "vu": "VU",
    "vulnerable": "VU",
    "en": "EN",
    "endangered": "EN",
    "cr": "CR",
    "critically endangered": "CR",
    "ew": "EW",
    "extinct in the wild": "EW",
    "ex": "EX",
    "extinct": "EX",
    "dd": "DD",
    "data deficient": "DD",
    "ne": "NE",
    "not evaluated": "NE",
    "not assessed": "NE",
    "unassessed": "NE",
    "unknown": "NE",
}

_IUCN_STATUS_LABELS: dict[str, str] = {
    "LC": "Least Concern",
    "NT": "Near Threatened",
    "VU": "Vulnerable",
    "EN": "Endangered",
    "CR": "Critically Endangered",
    "EW": "Extinct in the Wild",
    "EX": "Extinct",
    "DD": "Data Deficient",
    "NE": "Not Evaluated",
}

_FAMILY_THREAT_HINTS: dict[str, list[str]] = {
    "Accipitridae": [
        "Secondary poisoning from veterinary drugs such as diclofenac in livestock carcasses",
        "Electrocution and collision with power infrastructure",
        "Declining availability of wild ungulate carrion and open foraging habitat",
    ],
    "Otididae": [
        "Conversion of native grasslands and scrub to agriculture, solar farms, and industry",
        "Collision mortality on overhead power lines and fencing in open terrain",
        "Disturbance from grazing, roads, and military activity in breeding grounds",
    ],
    "Gruidae": [
        "Wetland drainage, dam construction, and agricultural encroachment on floodplain habitat",
        "Collision with power lines during migration and local movements",
        "Egg collection, nest disturbance, and pesticide exposure in croplands",
    ],
    "Anatidae": [
        "Wetland degradation, pollution, and hunting pressure along migration stopovers",
        "Climate-driven shifts in wetland hydroperiod affecting breeding success",
        "Bycatch and lead poisoning from spent shot in wetlands",
    ],
    "Phasianidae": [
        "Habitat fragmentation from expanding agriculture and urban edges",
        "Hunting and trapping pressure outside protected areas",
        "Predation and disturbance in degraded scrub and forest ecotones",
    ],
    "Passeridae": [
        "Urban green-space loss, pesticide use, and changing building architecture reducing nest sites",
        "Agricultural intensification reducing insect prey in farmland mosaics",
        "Heat stress and drought affecting nestling survival in open landscapes",
    ],
}

_GENERIC_MITIGATION_PHRASES = {
    "protect and restore key habitat",
    "protect and restore habitat",
    "reduce direct human disturbance",
    "reduce direct disturbance and mortality",
    "monitor populations and threats",
    "maintain targeted monitoring of local populations",
}


@dataclass
class SpeciesProfile:
    gbif_key: Optional[int]
    common_name: str
    scientific_name: str
    family: Optional[str] = None
    order_name: Optional[str] = None
    iucn_status: Optional[str] = None
    population_trend: Optional[str] = None
    population_size: Optional[str] = None
    habitat: list[str] = field(default_factory=list)
    range_summary: list[str] = field(default_factory=list)
    diet: Optional[str] = None
    breeding_behavior: Optional[str] = None
    migratory_behavior: Optional[str] = None
    source_urls: list[str] = field(default_factory=list)


@dataclass
class EvidenceItem:
    query: str
    title: str
    url: str
    snippet: str
    source: Optional[str] = None
    seendate: Optional[str] = None
    language: Optional[str] = None


def _clean_name(value: str) -> str:
    return " ".join(value.split()).strip()


def _normalize_conservation_status(status: Optional[str]) -> str:
    if not status or not str(status).strip():
        return "NE"
    raw = str(status).strip()
    lowered = raw.lower()
    if lowered in _IUCN_STATUS_ALIASES:
        return _IUCN_STATUS_ALIASES[lowered]
    upper = raw.upper()
    if upper in _IUCN_STATUS_LABELS:
        return upper
    for alias, code in _IUCN_STATUS_ALIASES.items():
        if alias in lowered:
            return code
    return raw


def _format_conservation_status(status: Optional[str]) -> str:
    code = _normalize_conservation_status(status)
    label = _IUCN_STATUS_LABELS.get(code)
    if label:
        return f"{code} ({label})"
    return code


def _family_threat_hints(family: Optional[str], order_name: Optional[str] = None) -> list[str]:
    if family and family in _FAMILY_THREAT_HINTS:
        return list(_FAMILY_THREAT_HINTS[family])
    order_hints = {
        "Accipitriformes": _FAMILY_THREAT_HINTS["Accipitridae"],
        "Otidiformes": _FAMILY_THREAT_HINTS["Otididae"],
        "Gruiformes": _FAMILY_THREAT_HINTS["Gruidae"],
        "Anseriformes": _FAMILY_THREAT_HINTS["Anatidae"],
        "Galliformes": _FAMILY_THREAT_HINTS["Phasianidae"],
        "Passeriformes": _FAMILY_THREAT_HINTS["Passeridae"],
    }
    if order_name and order_name in order_hints:
        return list(order_hints[order_name])
    return []


def _is_generic_list_item(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
    if not normalized:
        return True
    if normalized.startswith("heuristic:"):
        return True
    if normalized.startswith("gbif species profile"):
        return True
    return normalized in _GENERIC_MITIGATION_PHRASES


_PROMPT_ECHO_MARKERS = (
    "habitat terms",
    "range/country name",
    "range names",
    "occurrence_trend",
    "occurrence numbers",
    "evidence title",
    "named ecological trait",
    "ground key threats and mitigation",
    "ground the threats",
)


def _is_prompt_echo(text: str) -> bool:
    """
    Detects a model 'limited evidence reason' that restates the grounding-rubric
    categories from the system prompt (a checklist of *kinds* of facts) instead of
    naming an actual specific gap for the species. E.g. "No specific habitat terms,
    range/country names, numbers from occurrence_trend... are provided" is a restatement
    of the instructions, not a finding about the species, and should be dropped.
    """
    normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
    if not normalized:
        return False
    hits = sum(1 for marker in _PROMPT_ECHO_MARKERS if marker in normalized)
    return hits >= 2


def _is_species_relevant_evidence(item: EvidenceItem, profile: SpeciesProfile) -> bool:
    text = f"{item.title} {item.snippet}".lower()
    scientific = profile.scientific_name.lower()
    common = profile.common_name.lower()
    genus = scientific.split()[0].lower() if scientific else ""
    if scientific and scientific in text:
        return True
    if common and len(common) > 4 and common in text:
        return True
    if genus and len(genus) > 3 and genus in text:
        return True
    source = (item.source or "").lower()
    if source in {"gbif", "iucn red list", "iucn", "wikipedia", "curated input"}:
        return True
    return False


def _filter_relevant_evidence(evidence: list[EvidenceItem], profile: SpeciesProfile) -> list[EvidenceItem]:
    relevant = [
        item for item in evidence if _is_species_relevant_evidence(item, profile)]
    if relevant:
        return relevant
    return evidence[:4]


def _extract_threats_from_evidence(
    evidence: list[EvidenceItem],
    profile: SpeciesProfile,
    iucn_context: dict[str, Any],
) -> list[str]:
    threats: list[str] = []
    seen: set[str] = set()

    def add_threat(text: str) -> None:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned or cleaned.lower() in seen:
            return
        seen.add(cleaned.lower())
        threats.append(cleaned)

    iucn_threats = iucn_context.get("threats")
    if isinstance(iucn_threats, list):
        for threat in iucn_threats[:4]:
            add_threat(str(threat))
    elif isinstance(iucn_threats, str) and iucn_threats.strip():
        add_threat(iucn_threats.strip())

    threat_patterns = [
        (r"habitat loss|deforestation|fragmentation|land.?use|wetland drain|grassland conversion",
         "Habitat loss and land-use conversion affecting {species}"),
        (r"climate|drought|heat stress|rainfall|flood|extreme weather",
         "Climate variability and extreme weather stressing {species} populations"),
        (r"power line|electrocution|collision|wind turbine",
         "Collision and electrocution mortality on energy infrastructure"),
        (r"hunting|poaching|trade|trapping",
         "Direct mortality from hunting, trapping, or illegal trade"),
        (r"pesticide|poison|diclofenac|lead shot|toxic",
         "Poisoning and contaminant exposure in foraging or scavenging habitat"),
        (r"mining|road|development|industrial|solar",
         "Infrastructure and industrial development encroaching on remaining habitat"),
        (r"predation|nest disturbance|egg",
         "Breeding disturbance and nest-site vulnerability"),
    ]

    species_label = profile.common_name or profile.scientific_name
    reference_sources = {"gbif", "iucn red list",
                         "iucn", "wikipedia", "curated input"}
    for item in evidence[:8]:
        source_lower = (item.source or "").lower()
        if source_lower in reference_sources:
            # These are background/reference items (taxonomy, status, encyclopedia summary),
            # not threat findings — using them as filler threats produces nonsense like
            # "IUCN Red List: Critically Endangered..." appearing as a "key threat".
            continue
        blob = f"{item.title}. {item.snippet}".strip()
        if not blob:
            continue
        for pattern, template in threat_patterns:
            if re.search(pattern, blob, flags=re.IGNORECASE):
                add_threat(template.format(species=species_label))
                break
        # No else-branch here: if a genuine news item doesn't match a known threat
        # keyword, we skip it rather than fabricate a "threat" from its raw title —
        # that's what produced duplicated/tripled title text, especially for RSS
        # items with no <description> (where snippet was already set equal to title).

    if profile.habitat:
        add_threat(
            f"Dependence on {', '.join(profile.habitat[:2])} makes {species_label} vulnerable to localized habitat degradation"
        )
    if profile.range_summary:
        add_threat(
            f"Range restriction to {', '.join(profile.range_summary[:3])} concentrates risk for {species_label}"
        )

    if len(threats) < 2:
        for hint in _family_threat_hints(profile.family, profile.order_name)[:3]:
            add_threat(hint)

    return threats[:6]


def _build_species_specific_mitigation(
    threats: list[str],
    profile: SpeciesProfile,
    iucn_context: dict[str, Any],
) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    joined = " ".join(threats).lower()
    species_label = profile.common_name or profile.scientific_name

    def add_action(text: str) -> None:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if not cleaned or cleaned.lower() in seen:
            return
        seen.add(cleaned.lower())
        actions.append(cleaned)

    if profile.habitat:
        add_action(
            f"Protect and restore {', '.join(profile.habitat[:2])} within the known range of {species_label}"
        )
    elif "grassland" in joined or profile.family == "Otididae":
        add_action(
            f"Secure and manage open grassland and scrub corridors used by {species_label} for breeding and foraging"
        )
    elif "wetland" in joined or profile.family in {"Gruidae", "Anatidae"}:
        add_action(
            f"Maintain hydrological integrity of wetlands and floodplain mosaics critical to {species_label}"
        )

    if any(term in joined for term in ("collision", "electrocution", "power line", "infrastructure")):
        add_action(
            f"Retrofit or bury high-risk power lines and mark fences in {species_label} flyways and breeding grounds"
        )
    if any(term in joined for term in ("diclofenac", "poison", "pesticide", "lead shot", "toxic")):
        add_action(
            f"Regulate veterinary drugs, pesticides, and lead ammunition in landscapes where {species_label} forages"
        )
    if any(term in joined for term in ("hunting", "poaching", "trade", "trapping")):
        add_action(
            f"Strengthen anti-poaching patrols and community incentives to reduce direct take of {species_label}"
        )
    if any(term in joined for term in ("climate", "drought", "heat", "rainfall")):
        add_action(
            f"Identify climate refugia and drought buffers in the current range of {species_label}"
        )
    if profile.migratory_behavior and str(profile.migratory_behavior).strip().lower() not in {"false", "no", "none", "unknown"}:
        add_action(
            f"Coordinate cross-border safeguards along migration corridors used by {species_label}"
        )

    status = _normalize_conservation_status(
        profile.iucn_status or iucn_context.get(
            "category") or iucn_context.get("red_list_category")
    )
    if status in {"CR", "EN", "VU", "EW"}:
        add_action(
            f"Establish species-specific monitoring and rapid-response protocols for {species_label} at priority sites"
        )
    else:
        add_action(
            f"Track population trends and habitat quality for {species_label} through repeatable citizen-science and survey transects"
        )

    if iucn_context.get("source_url"):
        add_action(
            f"Cross-check management priorities against the current IUCN Red List assessment for {profile.scientific_name}"
        )

    if len(actions) < 3:
        add_action(
            f"Engage local landowners and protected-area managers to reduce disturbance in core {species_label} habitat"
        )

    return actions[:5]


def _build_species_queries(species: SpeciesProfile, country_code: Optional[str] = None) -> list[str]:
    queries: list[str] = []
    for template in _THREAT_QUERY_TEMPLATES:
        queries.append(f'"{species.scientific_name}" {template}')

    if species.common_name and species.common_name.lower() != species.scientific_name.lower():
        queries.append(f'"{species.common_name}" bird conservation threats')
        queries.append(
            f'"{species.common_name}" endangered population decline')

    if species.range_summary:
        for region in species.range_summary[:3]:
            queries.append(
                f'"{species.scientific_name}" "{region}" conservation threat')

    if species.habitat:
        for habitat in species.habitat[:3]:
            queries.append(
                f'"{species.scientific_name}" "{habitat}" habitat loss')

    if species.iucn_status:
        queries.append(
            f'"{species.scientific_name}" IUCN {_normalize_conservation_status(species.iucn_status)} population decline'
        )

    if species.population_trend:
        queries.append(
            f'"{species.scientific_name}" "{species.population_trend}" conservation')

    if species.migratory_behavior and str(species.migratory_behavior).strip().lower() not in {"false", "no", "none", "unknown"}:
        queries.append(
            f'"{species.scientific_name}" migration corridor climate change')

    if country_code:
        queries.append(
            f'"{species.scientific_name}" {country_code} conservation')

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        query = _clean_name(query)
        if query not in seen:
            seen.add(query)
            deduped.append(query)
    return deduped


async def _resolve_gbif_species(species_name: str, gbif_key: Optional[int] = None) -> SpeciesProfile:
    """Resolve a species profile through the shared GBIF adapter."""
    if not gbif_key:
        match = await gbif_source.match_species_key(species_name)
        gbif_key = match.data if match.ok else None

    if not gbif_key:
        return SpeciesProfile(gbif_key=None, common_name=species_name,
                              scientific_name=species_name, source_urls=[])

    detail = await gbif_source.species_detail(gbif_key)
    if not detail.ok or not detail.data:
        logger.warning("GBIF lookup failed for %s: %s", species_name, detail.error)
        return SpeciesProfile(gbif_key=gbif_key, common_name=species_name,
                              scientific_name=species_name, source_urls=[])

    data = detail.data
    iucn = await gbif_source.iucn_category(gbif_key)
    return SpeciesProfile(
        gbif_key=data.get("gbif_key"),
        common_name=data.get("common_name") or data.get("scientific_name") or species_name,
        scientific_name=data.get("scientific_name") or species_name,
        family=data.get("family"),
        order_name=data.get("order_name"),
        iucn_status=iucn.data if iucn.ok else None,
        habitat=[],
        range_summary=[],
        source_urls=[f"{GBIF_BASE}/species/{data.get('gbif_key')}"] if data.get("gbif_key") else [],
    )


async def _fetch_gbif_descriptions(gbif_key: int) -> dict[str, Any]:
    """Habitat and threat text blocks, grouped by description type."""
    res = await gbif_source.species_descriptions(gbif_key, limit=12)
    if not res.ok:
        return {}
    grouped: dict[str, list[str]] = {}
    for entry in res.data or []:
        text = re.sub(r"\s+", " ", str(entry.get("description") or "")).strip()
        if text:
            grouped.setdefault((entry.get("type") or "general").lower(), []).append(text)
    return grouped


async def _fetch_gbif_range_summary(gbif_key: int, country_code: Optional[str] = None) -> list[str]:
    """Countries the species is recorded in, most-recorded first."""
    res = await gbif_source.occurrence_country_facets(
        gbif_key, limit=8, country=country_code.upper() if country_code else None)
    if not res.ok:
        return []
    return [c["country"] for c in (res.data or []) if c.get("country")][:6]


async def _fetch_wikipedia_context(scientific_name: str, common_name: str) -> dict[str, Any]:
    """Species summary via the shared Wikipedia adapter."""
    if (common_name or "").lower() == "unknown bird":
        common_name = ""
    res = await evidence_source.wikipedia_summary(scientific_name, common_name)
    data = res.data or {}
    extract = re.sub(r"\s+", " ", str(data.get("extract") or "")).strip()
    if not extract:
        return {}
    return {"title": data.get("title") or scientific_name,
            "extract": extract[:700], "url": data.get("url")}


def _merge_unique_strings(existing: list[str], incoming: list[str], limit: int = 6) -> list[str]:
    merged = list(existing)
    seen = {value.lower() for value in merged}
    for value in incoming:
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        merged.append(cleaned)
        if len(merged) >= limit:
            break
    return merged


async def _enrich_species_profile(
    profile: SpeciesProfile,
    country_code: Optional[str] = None,
) -> tuple[SpeciesProfile, dict[str, Any]]:
    tasks: list[Any] = [_fetch_wikipedia_context(
        profile.scientific_name, profile.common_name)]
    if profile.gbif_key:
        tasks.append(_fetch_gbif_descriptions(profile.gbif_key))
        tasks.append(_fetch_gbif_range_summary(
            profile.gbif_key, country_code=country_code))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    wiki_context: dict[str, Any] = results[0] if len(
        results) > 0 and isinstance(results[0], dict) else {}
    gbif_desc: dict[str, Any] = results[1] if len(
        results) > 1 and isinstance(results[1], dict) else {}
    gbif_range: list[str] = results[2] if len(
        results) > 2 and isinstance(results[2], list) else []

    if gbif_desc:
        profile.habitat = _merge_unique_strings(
            profile.habitat, gbif_desc.get("habitat", []))
        profile.range_summary = _merge_unique_strings(
            profile.range_summary, gbif_desc.get("range_summary", []))
        profile.diet = profile.diet or gbif_desc.get("diet")
        profile.breeding_behavior = profile.breeding_behavior or gbif_desc.get(
            "breeding_behavior")
        profile.migratory_behavior = profile.migratory_behavior or gbif_desc.get(
            "migratory_behavior")

    if gbif_range:
        profile.range_summary = _merge_unique_strings(
            profile.range_summary, gbif_range)

    if wiki_context.get("extract"):
        extract = wiki_context["extract"]
        if not profile.habitat:
            habitat_match = re.search(
                r"(?:inhabits|found in|occurs in|lives in|breeds in)\s+([^.;]{8,120})",
                extract,
                flags=re.IGNORECASE,
            )
            if habitat_match:
                profile.habitat = _merge_unique_strings(
                    profile.habitat, [habitat_match.group(1).strip()])
        if not profile.range_summary:
            range_match = re.search(
                r"(?:native to|distributed across|found across|occurs in)\s+([^.;]{8,120})",
                extract,
                flags=re.IGNORECASE,
            )
            if range_match:
                profile.range_summary = _merge_unique_strings(
                    profile.range_summary, [range_match.group(1).strip()])
        if "migrat" in extract.lower() and not profile.migratory_behavior:
            profile.migratory_behavior = "Migratory or partially migratory per reference summary"
        profile.source_urls = _merge_unique_strings(
            profile.source_urls,
            [wiki_context["url"]] if wiki_context.get("url") else [],
            limit=4,
        )

    return profile, wiki_context


def _build_structured_fallback_evidence(
    profile: SpeciesProfile,
    iucn_context: dict[str, Any],
    wiki_context: Optional[dict[str, Any]] = None,
) -> list[EvidenceItem]:
    fallback: list[EvidenceItem] = []

    if profile.source_urls:
        fallback.append(
            EvidenceItem(
                query=f"GBIF profile for {profile.scientific_name}",
                title=f"GBIF species profile: {profile.common_name}",
                url=profile.source_urls[0],
                snippet=(
                    f"{profile.common_name} ({profile.scientific_name}) is classified in "
                    f"{profile.family or 'an unknown family'}, order {profile.order_name or 'Unknown'}."
                ),
                source="GBIF",
            )
        )

    if iucn_context:
        status = _format_conservation_status(
            iucn_context.get("category") or iucn_context.get(
                "red_list_category") or profile.iucn_status
        )
        trend = iucn_context.get(
            "population_trend") or profile.population_trend or "Unknown"
        threat_text = ""
        threats = iucn_context.get("threats")
        if isinstance(threats, list) and threats:
            threat_text = "; ".join(str(item) for item in threats[:3])
        elif isinstance(threats, str):
            threat_text = threats
        fallback.append(
            EvidenceItem(
                query=f"IUCN profile for {profile.scientific_name}",
                title=f"IUCN Red List: {iucn_context.get('iucn_title') or profile.common_name}",
                url=iucn_context.get(
                    "source_url") or f"{settings.iucn_base_url}/species/{profile.scientific_name}",
                snippet=(
                    f"IUCN status for {profile.common_name} is {status}; population trend is {trend}."
                    + (f" Documented threats include {threat_text}." if threat_text else "")
                ),
                source="IUCN Red List",
            )
        )

    if wiki_context and wiki_context.get("extract"):
        fallback.append(
            EvidenceItem(
                query=f"Wikipedia summary for {profile.scientific_name}",
                title=f"Wikipedia: {wiki_context.get('title') or profile.common_name}",
                url=wiki_context.get("url") or "",
                snippet=wiki_context["extract"][:320],
                source="Wikipedia",
            )
        )

    if profile.habitat or profile.range_summary:
        fallback.append(
            EvidenceItem(
                query=f"Ecological profile for {profile.scientific_name}",
                title=f"Ecological profile: {profile.common_name}",
                url=profile.source_urls[0] if profile.source_urls else GBIF_BASE,
                snippet=(
                    f"Habitat notes: {', '.join(profile.habitat) if profile.habitat else 'Unknown'}. "
                    f"Range notes: {', '.join(profile.range_summary) if profile.range_summary else 'Unknown'}."
                ),
                source="Curated input",
            )
        )

    return fallback


async def _search_gdelt(query: str, max_records: int = 6) -> list[EvidenceItem]:
    """
    News evidence from GDELT.

    Throttling, the post-429 cooldown and the private cache this used to carry
    are now the shared layer's job — GDELT's concurrency cap and Retry-After
    handling live with its registry entry.
    """
    res = await evidence_source.gdelt(query, max_records)
    return [_evidence_from_dict(item) for item in (res.data or [])]


def _evidence_from_dict(item: dict) -> EvidenceItem:
    return EvidenceItem(
        query=item.get("query", ""),
        title=item.get("title", "Untitled article"),
        url=item.get("url", ""),
        snippet=item.get("snippet") or item.get("title", ""),
        source=item.get("source", "unknown"),
        seendate=item.get("seendate"),
        language=item.get("language", "en"),
    )


def _rss_locale_for_country(country_code: Optional[str]) -> tuple[str, str]:
    if country_code and len(country_code.strip()) == 2:
        cc = country_code.strip().upper()
        return cc, f"{cc}:en"
    return "US", "US:en"


async def _search_news_rss(query: str, max_records: int = 6,
                           country_code: Optional[str] = None) -> list[EvidenceItem]:
    res = await evidence_source.news_rss(query, max_records, country_code)
    return [_evidence_from_dict(item) for item in (res.data or [])]


def _parse_public_iucn_search(scientific_name: str, html_text: str) -> dict[str, Any]:
    flattened = re.sub(r"\s+", " ", html_text)
    name_pattern = re.escape(scientific_name)

    patterns = [
        rf'animalia\s+-\s+aves\s+global\s+##\s*(?P<common>.+?)\s+_{name_pattern}_\s+(?P<trend>Unknown|Stable|Decreasing|Increasing)\[(?P<category>[a-z]{{2}})\]\((?P<url>https://www\.iucnredlist\.org/species/\d+/\d+)\s+"(?P<title>[^"]+)"\)',
        rf'_{name_pattern}_\s+(?P<trend>Unknown|Stable|Decreasing|Increasing)\[(?P<category>[a-z]{{2}})\]\((?P<url>https://www\.iucnredlist\.org/species/\d+/\d+)\s+"(?P<title>[^"]+)"\)',
        rf'_{name_pattern}_.*?\[(?P<category>[a-z]{{2}})\]\((?P<url>https://www\.iucnredlist\.org/species/\d+/\d+)\s+"(?P<title>[^"]+)"\)',
    ]

    for pattern in patterns:
        match = re.search(pattern, flattened, flags=re.IGNORECASE)
        if not match:
            continue
        trend = match.groupdict().get("trend") or "Unknown"
        return {
            "category": match.group("category").upper(),
            "red_list_category": match.group("category").upper(),
            "population_trend": trend.capitalize(),
            "source_url": match.group("url"),
            "common_name": (match.groupdict().get("common") or "").strip() or None,
            "iucn_title": match.group("title").strip(),
        }

    category_match = re.search(
        rf"{name_pattern}.*?\b(LC|NT|VU|EN|CR|EW|EX|DD|NE)\b",
        flattened,
        flags=re.IGNORECASE,
    )
    url_match = re.search(
        r"https://www\.iucnredlist\.org/species/\d+/\d+", flattened)
    if category_match:
        category = category_match.group(1).upper()
        return {
            "category": category,
            "red_list_category": category,
            "population_trend": None,
            "source_url": url_match.group(0) if url_match else None,
            "iucn_title": scientific_name,
        }

    return {}


async def _fetch_public_iucn_context(scientific_name: str) -> dict[str, Any]:
    """IUCN status parsed from the public site, when no API token is set."""
    res = await evidence_source.iucn_status(scientific_name)
    data = res.data or {}
    if not data.get("category"):
        return {}
    return {
        "category": data.get("category"),
        "population_trend": data.get("population_trend"),
        "source_url": data.get("source_url"),
        "source": res.provenance.source,
    }


async def _fetch_wikidata_iucn_status(scientific_name: str) -> dict[str, Any]:
    res = await evidence_source.wikidata_iucn(scientific_name)
    data = res.data or {}
    if not data.get("category"):
        return {}
    return {
        "category": data.get("category"),
        "label": data.get("label"),
        "source_url": data.get("source_url"),
        "source": "wikidata",
    }


async def _fetch_gbif_occurrence_trend(gbif_key: Optional[int], country_code: Optional[str] = None) -> dict[int, int]:
    """
    Per-year GBIF occurrence-record counts for the species.

    This is a proxy for recording effort and detectability rather than true
    population size, but it gives the report model concrete, verifiable numbers
    to reason with instead of vague language.
    """
    if not gbif_key:
        return {}
    res = await gbif_source.occurrence_counts_by_year(
        gbif_key, 2010, 2024, country=country_code.upper() if country_code else None)
    if not res.ok:
        return {}
    return {p["year"]: p["count"] for p in (res.data or []) if p.get("count")}


async def _fetch_iucn_context(scientific_name: str) -> dict[str, Any]:
    """
    IUCN status, trying each route in descending authority.

    The keyed API, then the public site, then Wikidata — the fallback chain
    itself now lives in the data layer, so token handling and status-code
    fallbacks are not duplicated here.
    """
    res = await repo.conservation_status(scientific_name)
    data = res.data or {}
    if not data.get("category"):
        return {}
    return {**data, "source": res.provenance.source}


def _heuristics_from_evidence(evidence: list[EvidenceItem]) -> dict[str, Any]:
    joined = " ".join(
        f"{item.title} {item.snippet}" for item in evidence).lower()
    threats: list[str] = []
    for label, keywords in [
        ("habitat_loss", ["deforestation", "habitat loss",
         "wetland", "fragmentation", "drainage"]),
        ("climate_impacts", ["climate", "drought",
         "heat", "rainfall", "flood", "extreme weather"]),
        ("direct_mortality", ["hunting", "poaching",
         "trade", "collision", "electrocution"]),
        ("policy_or_development_pressure", [
         "policy", "development", "road", "mining", "protected area"]),
    ]:
        if any(keyword in joined for keyword in keywords):
            threats.append(label)

    return {
        "risk_direction": "elevating" if threats else "uncertain",
        "threat_labels": threats,
    }


def _build_limited_evidence_reasons(
    profile: SpeciesProfile,
    evidence: list[EvidenceItem],
    iucn_context: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    evidence_count = len(evidence)
    if evidence_count == 0:
        reasons.append(
            "No recent news or article evidence was available from external sources.")
    elif evidence_count < 3:
        reasons.append(
            f"Limited external evidence ({evidence_count} items) was available for corroboration.")

    news_count = sum(
        1
        for item in evidence
        if (item.url or "").startswith("https://news.google.com/")
        or (item.source or "").lower().startswith("google news")
        or "news.google.com" in (item.url or "")
    )
    gdelt_count = sum(1 for item in evidence if item.source and str(
        item.source).lower().startswith("gdelt"))
    if news_count == 0:
        reasons.append(
            "No species-specific articles were found in Google News RSS.")
    if gdelt_count == 0:
        reasons.append(
            "No corroborating articles were found in GDELT within the search scope.")

    if not iucn_context:
        reasons.append(
            "IUCN Red List context was not accessible; conservation status is based on alternative sources.")

    if not profile.population_trend and not profile.population_size:
        reasons.append(
            "Population trend and size data were not available in the species record.")
    if not profile.habitat:
        reasons.append(
            "Habitat information was not available in the species record.")
    if not profile.range_summary:
        reasons.append(
            "Range summary was not available in the species record.")

    deduped: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        if reason not in seen:
            seen.add(reason)
            deduped.append(reason)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in sources:
        key = f"{source.get('url') or ''}|{source.get('title') or ''}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def _salvage_partial_report(raw_text: str) -> dict[str, Any]:
    start = raw_text.find("{")
    if start < 0:
        return {}

    candidate = raw_text[start:]
    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(candidate)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    for end_index in range(1, len(candidate) + 1):
        try:
            parsed = json.loads(candidate[:end_index])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    for end_index in range(1, len(candidate) + 1):
        try:
            parsed = json.loads(candidate[:end_index].rstrip(","))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    return {}


def _parse_structured_response(raw_response: str) -> tuple[dict[str, Any], str]:
    """
    Clean, parse, and classify a Stage-A structured-JSON model response in one place.
    Returns (parsed_dict, model_output_status). parsed_dict is {} when nothing usable
    could be recovered.
    """
    cleaned = _strip_fences(raw_response)
    cleaned = _repair_json_text(cleaned)
    if not cleaned.strip():
        return {}, "empty"

    try:
        loaded = json.loads(cleaned)
    except json.JSONDecodeError:
        loaded = _salvage_partial_report(cleaned)

    if not isinstance(loaded, dict) or not loaded:
        return {}, "invalid_json"

    return loaded, _classify_structured_report(loaded)


def _normalize_model_payload(parsed: Any, profile: SpeciesProfile, iucn_context: dict[str, Any], evidence: list[EvidenceItem]) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}

    normalized: dict[str, Any] = {}
    if isinstance(parsed.get("decision_support_draft"), str):
        normalized["decision_support_draft"] = parsed["decision_support_draft"]
    elif isinstance(parsed.get("report"), str):
        normalized["decision_support_draft"] = parsed["report"]
    elif isinstance(parsed.get("summary"), str):
        normalized["decision_support_draft"] = parsed["summary"]

    status_value = parsed.get("current_conservation_status") or parsed.get(
        "status") or parsed.get("conservation_status")
    if isinstance(status_value, str) and status_value.strip():
        normalized["current_conservation_status"] = _format_conservation_status(
            status_value.strip())

    threats = parsed.get("key_threats") or parsed.get(
        "threats") or parsed.get("threat_factors")
    if isinstance(threats, list):
        normalized["key_threats"] = [str(item).strip()
                                     for item in threats if str(item).strip()]
    elif isinstance(threats, dict):
        normalized["key_threats"] = [str(threats).strip()]

    survivability = parsed.get("survivability_assessment") or parsed.get(
        "recommendations") or parsed.get("assessment")
    if isinstance(survivability, str) and survivability.strip():
        normalized["survivability_assessment"] = survivability.strip()
    elif isinstance(survivability, list):
        normalized["survivability_assessment"] = " ".join(
            str(item).strip() for item in survivability if str(item).strip())

    mitigation_actions = parsed.get(
        "mitigation_actions") or parsed.get("conservation_actions")
    if isinstance(mitigation_actions, list):
        normalized["mitigation_actions"] = [
            str(item).strip() for item in mitigation_actions if str(item).strip()]
    elif isinstance(mitigation_actions, str) and mitigation_actions.strip():
        normalized["mitigation_actions"] = [mitigation_actions.strip()]

    sources = parsed.get("sources")
    if isinstance(sources, list):
        normalized["sources"] = sources

    limited = parsed.get("limited_evidence_reasons")
    if isinstance(limited, list):
        normalized["limited_evidence_reasons"] = [
            str(item).strip() for item in limited if str(item).strip()]

    reviewer_notes = parsed.get("reviewer_notes")
    if isinstance(reviewer_notes, str) and reviewer_notes.strip():
        normalized["reviewer_notes"] = reviewer_notes.strip()

    if not normalized.get("decision_support_draft"):
        if isinstance(parsed.get("species"), dict):
            species_data = parsed["species"]
            name = species_data.get("name") or species_data.get(
                "scientific_name") or species_data.get("common_name") or profile.scientific_name
            status_text = parsed.get("status") or parsed.get(
                "current_conservation_status") or parsed.get("conservation_status") or ""
            normalized[
                "decision_support_draft"] = f"Species: {name}\nStatus: {status_text}\nThreats: {json.dumps(parsed.get('threats') or parsed.get('threat_factors') or [], ensure_ascii=False)}"

    if not normalized.get("survivability_assessment") and normalized.get("current_conservation_status"):
        normalized["survivability_assessment"] = _build_survivability_text(
            normalized["current_conservation_status"], profile, iucn_context
        )

    return normalized


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _classify_model_exception(exc: Exception) -> str:
    message = str(exc).lower()
    if "timeout" in message:
        return "timeout"
    if "not available" in message or "not reachable" in message or "connection" in message:
        return "unavailable"
    if "http error" in message:
        return "http_error"
    return "error"


def _classify_parsed_report(parsed: dict[str, Any]) -> str:
    essential_fields = [
        parsed.get("decision_support_draft"),
        parsed.get("current_conservation_status"),
        parsed.get("survivability_assessment"),
    ]
    present_count = sum(1 for value in essential_fields if _has_text(value))
    if present_count == len(essential_fields):
        return "complete"
    if present_count >= 2:
        return "partial"
    return "invalid_json"


def _classify_structured_report(parsed: dict[str, Any]) -> str:
    """
    Classify the short structured-stage response (no decision_support_draft — that's
    produced separately by the draft stage). "complete" requires a usable status,
    survivability assessment, and at least one non-generic threat and mitigation.
    """
    if not parsed:
        return "invalid_json"
    has_status = _has_text(parsed.get("current_conservation_status"))
    has_assessment = _has_text(parsed.get("survivability_assessment"))
    has_threats = bool(parsed.get("key_threats"))
    has_mitigation = bool(parsed.get("mitigation_actions"))
    if has_status and has_assessment and has_threats and has_mitigation:
        return "complete"
    if has_status or has_assessment or has_threats or has_mitigation:
        return "partial"
    return "invalid_json"


def _generation_mode_for_status(model_output_status: str) -> str:
    if model_output_status == "complete":
        return "model_synthesis"
    if model_output_status == "partial":
        return "hybrid_recovery"
    return "evidence_based_recovery"


def _contains_failure_language(text: Any) -> bool:
    if not _has_text(text):
        return False

    normalized = re.sub(r"\s+", " ", str(text)).strip().lower()
    suspicious_phrases = [
        "fallback draft",
        "feature failed",
        "report generation failed",
        "model output was unavailable",
        "model path was unavailable",
        "returned unusable output",
        "assessment unavailable from the local model",
        "local model was unavailable",
    ]
    return any(phrase in normalized for phrase in suspicious_phrases)


def _build_reviewer_notes(
    evidence_count: int,
    model_output_status: str,
) -> str:
    if model_output_status == "complete":
        return (
            f"Live species evidence and reference records were synthesized with the local model. "
            f"Review the cited sources and noted evidence limitations before conservation use. "
            f"Evidence items reviewed: {evidence_count}."
        )

    if model_output_status == "partial":
        return (
            f"Live species evidence was collected successfully ({evidence_count} items), and the final report keeps that evidence in place. "
            f"The local model returned only a partial structured response, so EcoPath completed the draft from the available live sources and reference records."
        )

    if model_output_status in {"invalid_json", "empty", "timeout", "unavailable", "http_error", "error"}:
        return (
            f"Live species evidence was collected successfully ({evidence_count} items), and the report remains usable. "
            f"The local model could not provide a clean structured synthesis in this run, so EcoPath assembled the draft directly from the collected evidence and reference records."
        )

    return (
        f"Live species evidence was collected successfully ({evidence_count} items). "
        f"This report is a reviewer-facing draft assembled from the available evidence and reference records."
    )


def _build_survivability_text(
    status: str,
    profile: Optional[SpeciesProfile] = None,
    iucn_context: Optional[dict[str, Any]] = None,
) -> str:
    normalized = _normalize_conservation_status(status)
    species_label = profile.common_name if profile else "this species"
    habitat_text = ", ".join(
        profile.habitat[:2]) if profile and profile.habitat else "its core habitat"
    trend = (
        (profile.population_trend if profile else None)
        or (iucn_context or {}).get("population_trend")
        or "unknown"
    )

    if normalized in {"LC", "NT"}:
        return (
            f"{species_label} currently appears broadly secure under IUCN category {normalized}, but populations remain sensitive to changes in {habitat_text}, "
            f"disturbance, and climate stress. Reported trend: {trend}. Continued monitoring is warranted, especially at range edges."
        )
    if normalized in {"VU", "EN", "CR", "EW"}:
        return (
            f"{species_label} faces meaningful extinction risk under IUCN category {normalized}. Dependence on {habitat_text}, combined with a {trend} population trend, "
            f"suggests that targeted habitat protection and threat reduction should be treated as a conservation priority."
        )
    if normalized == "DD":
        return (
            f"{species_label} is data deficient ({normalized}), meaning the available records are insufficient for a confident trend estimate. "
            f"Priority should be given to filling survey gaps across {habitat_text} before major management decisions."
        )
    return (
        f"{species_label} lacks a confirmed Red List category in the retrieved sources (currently treated as {normalized}). "
        f"The species should be monitored closely in {habitat_text} and reassessed against authoritative databases."
    )


def _build_reference_sources(profile: SpeciesProfile, iucn_context: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    gbif_url = profile.source_urls[0] if profile.source_urls else (
        f"{GBIF_BASE}/species/{profile.gbif_key}" if profile.gbif_key else GBIF_BASE
    )
    sources.append(
        {
            "query": "GBIF species profile",
            "title": f"GBIF species profile: {profile.common_name}",
            "url": gbif_url,
            "snippet": "Primary taxonomic reference used to anchor the species identity and metadata.",
            "source": "GBIF",
            "seendate": None,
            "language": None,
        }
    )

    iucn_url = iucn_context.get("source_url")
    if iucn_url:
        sources.append(
            {
                "query": profile.scientific_name,
                "title": f"IUCN Red List: {iucn_context.get('iucn_title') or profile.common_name}",
                "url": iucn_url,
                "snippet": f"IUCN status: {iucn_context.get('red_list_category') or iucn_context.get('category') or 'Unknown'}; population trend: {iucn_context.get('population_trend') or 'Unknown'}.",
                "source": "IUCN Red List",
                "seendate": None,
                "language": None,
            }
        )

    return _dedupe_sources(sources)


def _call_ollama_report_model_cli(messages: list[dict[str, str]]) -> str:
    prompt_lines: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            prompt_lines.append(f"System: {content}")
        elif role == "user":
            prompt_lines.append(f"User: {content}")
        else:
            prompt_lines.append(f"{role.title()}: {content}")

    prompt_text = "\n\n".join(prompt_lines)
    try:
        completed = subprocess.run(
            ["ollama", "run", settings.ollama_report_model],
            input=prompt_text,
            text=True,
            capture_output=True,
            timeout=600,
            check=False,
        )
    except FileNotFoundError as exc:
        raise Exception("Ollama CLI is not available on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise Exception("Ollama CLI timed out") from exc

    if completed.returncode == 0 and completed.stdout.strip():
        return completed.stdout.strip()

    stderr_text = (completed.stderr or "").strip()
    raise Exception(
        f"Ollama CLI returned exit code {completed.returncode}: {stderr_text or 'no output'}")


async def _call_ollama_report_model(
    messages: list[dict[str, str]],
    num_predict: int = 1400,
    want_json: bool = True,
    temperature: float = 0.2,
) -> str:
    payload: dict[str, Any] = {
        "model": settings.ollama_report_model,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": num_predict,
        },
    }
    if want_json:
        payload["format"] = "json"

    # Transport, retry and the single-flight concurrency cap live in the data
    # layer; this keeps only the CLI fallback, which is specific to Ollama
    # being installed locally but not serving HTTP.
    if not await ollama_source.is_up():
        logger.warning("Ollama HTTP endpoint unavailable at %s; trying CLI fallback",
                       settings.ollama_base_url)
        return await asyncio.to_thread(_call_ollama_report_model_cli, messages)

    result = await ollama_source.chat(
        messages, temperature=temperature, num_predict=num_predict, want_json=want_json,
    )
    if result.ok:
        return result.data

    logger.warning("Ollama generation failed (%s); falling back to CLI", result.error)
    return await asyncio.to_thread(_call_ollama_report_model_cli, messages)


async def warm_report_model() -> None:
    try:
        await asyncio.wait_for(
            _call_ollama_report_model(
                [
                    {"role": "system", "content": _build_structured_system_prompt()},
                    {"role": "user", "content": "Warm the model. Reply with a minimal JSON object containing a single key named ready with value true."},
                ]
            ),
            timeout=180.0,
        )
    except Exception as exc:
        logger.warning("Report model warm-up skipped: %s", exc)


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        fenced = re.findall(r"```(?:json)?\s*(.*?)\s*```",
                            raw, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced[0].strip()
        parts = raw.split("```")
        if len(parts) >= 3:
            return parts[1].strip()
    return raw


def _repair_json_text(raw: str) -> str:
    cleaned = raw.strip()
    if not cleaned:
        return cleaned

    if cleaned.startswith("{"):
        try:
            json.loads(cleaned)
            return cleaned
        except json.JSONDecodeError:
            pass

    start = cleaned.find("{")
    if start >= 0:
        cleaned = cleaned[start:]

    result: list[str] = []
    brace_depth = 0
    in_string = False
    escape = False
    for char in cleaned:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            elif char in "\r\n":
                result.append("\\n")
                continue
            result.append(char)
            continue

        if char == '"':
            in_string = True
            result.append(char)
        elif char == "{":
            brace_depth += 1
            result.append(char)
        elif char == "}":
            brace_depth -= 1
            result.append(char)
            if brace_depth == 0:
                break
        else:
            result.append(char)

    repaired = "".join(result)
    if brace_depth > 0 and not repaired.rstrip().endswith("}"):
        repaired = repaired.rstrip() + "}" * brace_depth

    if repaired.startswith("{"):
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            pass

    for end_idx in range(1, len(cleaned) + 1):
        attempt = cleaned[:end_idx]
        if attempt.startswith("{"):
            try:
                json.loads(attempt)
                return attempt
            except json.JSONDecodeError:
                continue

    return cleaned


_GENERIC_PHRASES_FOR_PROMPT = sorted(_GENERIC_MITIGATION_PHRASES)

_STRUCTURED_FEWSHOT_EXAMPLE = {
    "input_species": "Sarus Crane (Antigone antigone), family Gruidae, habitat: freshwater marshes and paddy fields, range: northern and central India, migratory_behavior: largely resident/local movements, iucn_status: VU, occurrence_trend: {\"2020\": 412, \"2021\": 355, \"2022\": 301}",
    "output": {
        "current_conservation_status": "VU (Vulnerable)",
        "key_threats": [
            "GBIF occurrence records for the Sarus Crane fell from 412 (2020) to 301 (2022) across its northern Indian range, consistent with continued wetland loss rather than just reduced recording effort",
            "Drainage and conversion of the freshwater marshes and seasonal wetlands the species nests in for paddy and other agriculture removes both foraging and breeding habitat in the same landscapes",
            "Nests are built in open, exposed marsh and field edges, so they are frequently lost to trampling by livestock, mechanized harvesting, and human disturbance during the breeding season",
            "As a large, slow-flying resident bird sharing agricultural landscapes with people, it is vulnerable to collision with power lines strung across its wetland-farmland corridors"
        ],
        "mitigation_actions": [
            "Work with farmers in the Sarus Crane's core range to identify and protect active nest sites through the breeding season, since most nests are on private agricultural land rather than in protected areas",
            "Restore and legally safeguard seasonal wetlands used for feeding and roosting, particularly the marsh-paddy mosaics identified in its known range",
            "Mark or reroute the highest-risk overhead power lines that cross wetland-to-field flight paths in its breeding grounds",
            "Continue systematic occurrence monitoring (e.g. repeatable GBIF/eBird-style counts) to confirm whether the 2020-2022 decline reflects a true population trend or a reporting artifact"
        ],
        "survivability_assessment": "The Sarus Crane is classified Vulnerable, and the available occurrence data show a declining trend over 2020-2022 concentrated in its northern Indian wetland-farmland range. Because it nests in unprotected agricultural wetlands rather than reserves, its near-term outlook depends heavily on how those specific landscapes are managed rather than on broad national policy alone.",
        "limited_evidence_reasons": [],
        "reviewer_notes": "Assessment grounded in GBIF occurrence counts, IUCN status, and habitat/range profile for this species; no news evidence was required to support the above."
    },
}


def _build_structured_system_prompt() -> str:
    return (
        "You are a senior avian conservation analyst. You will receive a JSON payload describing ONE specific "
        "bird species (profile, IUCN context, GBIF occurrence trend, and retrieved evidence). Your job is to "
        "produce a short, tightly-grounded analytic JSON object about THIS species only.\n\n"
        "Hard rules:\n"
        "1. GROUNDING: before writing each item in key_threats and mitigation_actions, pick one fact that is "
        "actually present in this species' payload (something from its habitat, range, occurrence_trend numbers, "
        "an evidence snippet, or its diet/breeding/migration notes) and build the sentence around that fact. "
        "A sentence that could be copy-pasted onto a different bird in the same family without edits is not "
        "acceptable — rewrite it until it could not.\n"
        "2. NO STOCK PHRASES: never output any of these generic phrases verbatim or as a close paraphrase: "
        f"{json.dumps(_GENERIC_PHRASES_FOR_PROMPT)}. These are exactly what a lazy/templated report looks like.\n"
        "3. NUMBERS: if occurrence_trend is provided, cite specific years and counts (e.g. 'GBIF records fell "
        "from N in 2019 to M in 2023') as a proxy for detectability/recording trend — always caveat that this is "
        "recording effort, not a direct population census. Never invent a population number, date, or citation "
        "that is not in the payload.\n"
        "4. MISSING DATA: limited_evidence_reasons must name the one or two SPECIFIC things you genuinely could "
        "not find for THIS species — e.g. 'no population size estimate was available' or 'no recent news "
        "coverage exists for this species' — each as a short, plain sentence about the species, not about the "
        "instructions you were given. NEVER restate, list, or paraphrase the categories mentioned in rule 1 "
        "above (do not write things like 'no habitat terms, range names, or occurrence numbers were provided') "
        "— that describes this prompt, not the species, and is not useful to a reviewer. If nothing is missing, "
        "return an empty list.\n"
        "5. current_conservation_status must be an IUCN code (LC, NT, VU, EN, CR, EW, EX, DD, NE) taken from the "
        "payload's iucn context or species profile — do not invent a status that is not present there.\n"
        "6. key_threats: 3-5 items. mitigation_actions: 3-5 items, each one directly countering one of the "
        "listed threats. survivability_assessment: 2-4 sentences covering trend, habitat sensitivity, and "
        "near-term risk, specific to this species.\n"
        "7. Output ONLY a single compact JSON object with exactly these keys: current_conservation_status, "
        "key_threats, mitigation_actions, survivability_assessment, limited_evidence_reasons, reviewer_notes. "
        "No markdown fences, no commentary before or after the JSON.\n\n"
        "Here is one worked example for a different species, showing the expected level of specificity "
        "(do not reuse its wording — it is only a style/grounding reference):\n"
        f"INPUT: {_STRUCTURED_FEWSHOT_EXAMPLE['input_species']}\n"
        f"OUTPUT: {json.dumps(_STRUCTURED_FEWSHOT_EXAMPLE['output'], ensure_ascii=True)}\n\n"
        "Example of a BAD limited_evidence_reasons entry (never write anything shaped like this — it restates "
        "this prompt instead of describing the species): "
        "\"No specific habitat terms, range names, or occurrence numbers were provided to ground the threats.\"\n"
        "Example of a GOOD limited_evidence_reasons entry for a different species: "
        "\"No population size estimate was available for this species in the supplied records.\""
    )


def _build_draft_system_prompt() -> str:
    return (
        "You are a senior avian conservation analyst writing the final section of a decision-support report for "
        "ONE specific bird species. You will receive the species profile and an already-approved analytic summary "
        "(status, key threats, mitigation actions, survivability assessment) for this exact species.\n\n"
        "Write a single markdown document with these headings, in this order: "
        "'## Species snapshot', '## Conservation status', '## Ecological context', '## Key threats', "
        "'## Survivability outlook', '## Recommended actions', '## Evidence notes'.\n"
        "Use the supplied key_threats and mitigation_actions as the content of those sections (you may smooth "
        "the prose, but do not remove the species-specific details in them or replace them with generic language). "
        "Reference the species by name throughout — this must read as written for this exact bird, not a template. "
        "Do not invent facts, numbers, or sources beyond what is supplied. Output ONLY the markdown document, "
        "no JSON, no code fences, no preamble."
    )


def _build_user_payload(
    profile: SpeciesProfile,
    iucn_context: dict[str, Any],
    evidence: list[EvidenceItem],
    heuristics: dict[str, Any],
    wiki_context: Optional[dict[str, Any]] = None,
    occurrence_trend: Optional[dict[int, int]] = None,
) -> dict[str, Any]:
    compact_evidence = []
    for item in evidence[:10]:
        compact_evidence.append({
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet[:320],
            "source": item.source,
        })

    iucn_block: dict[str, Any] = {}
    if iucn_context:
        iucn_block = {
            "category": iucn_context.get("category") or iucn_context.get("red_list_category"),
            "population_trend": iucn_context.get("population_trend") or profile.population_trend,
            "systems": iucn_context.get("systems"),
            "threats": iucn_context.get("threats"),
            "countries": iucn_context.get("countries"),
            "source_url": iucn_context.get("source_url"),
        }

    return {
        "task": (
            f"Analyze extinction risk for {profile.common_name} "
            f"({profile.scientific_name}). The analysis must read as if prepared for this exact bird, "
            f"not a generic template."
        ),
        "species": {
            "common_name": profile.common_name,
            "scientific_name": profile.scientific_name,
            "family": profile.family,
            "order_name": profile.order_name,
            "iucn_status": _normalize_conservation_status(profile.iucn_status),
            "population_trend": profile.population_trend,
            "population_size": profile.population_size,
            "habitat": profile.habitat[:4],
            "range_summary": profile.range_summary[:4],
            "diet": profile.diet,
            "breeding_behavior": profile.breeding_behavior,
            "migratory_behavior": profile.migratory_behavior,
        },
        "reference_summary": wiki_context.get("extract") if wiki_context else None,
        "iucn_context": iucn_block,
        "occurrence_trend": occurrence_trend or {},
        "evidence": compact_evidence,
        "heuristics": heuristics,
        "writing_requirements": {
            "mention_species_name_in_each_threat": True,
            "avoid_generic_mitigation_templates": True,
            "cite_evidence_by_title_in_draft": True,
        },
    }


def _structured_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_structured_system_prompt()},
        {"role": "user", "content": json.dumps(
            payload, ensure_ascii=True, indent=2)},
    ]


def _structured_repair_messages(payload: dict[str, Any], bad_output: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": _build_structured_system_prompt()},
        {"role": "user", "content": json.dumps(
            payload, ensure_ascii=True, indent=2)},
        {"role": "assistant", "content": bad_output[:1500]},
        {
            "role": "user",
            "content": (
                "That reply was not valid JSON (or did not match the required keys). "
                "Reply again with ONLY the JSON object, compact, no markdown fences, no commentary, "
                "using exactly the keys: current_conservation_status, key_threats, mitigation_actions, "
                "survivability_assessment, limited_evidence_reasons, reviewer_notes."
            ),
        },
    ]


def _draft_messages(payload: dict[str, Any], structured: dict[str, Any]) -> list[dict[str, str]]:
    draft_input = dict(payload)
    draft_input["approved_analysis"] = {
        "current_conservation_status": structured.get("current_conservation_status"),
        "key_threats": structured.get("key_threats"),
        "mitigation_actions": structured.get("mitigation_actions"),
        "survivability_assessment": structured.get("survivability_assessment"),
    }
    return [
        {"role": "system", "content": _build_draft_system_prompt()},
        {"role": "user", "content": json.dumps(
            draft_input, ensure_ascii=True, indent=2)},
    ]


def _render_markdown_draft(
    profile: SpeciesProfile,
    status_code: str,
    status_label: str,
    key_threats: list[str],
    mitigation_actions: list[str],
    survivability_text: str,
    iucn_context: dict[str, Any],
    evidence: list[EvidenceItem],
) -> str:
    """
    Render the long-form markdown draft from whichever key_threats/mitigation_actions/
    status ended up being final for this report — evidence-based fallback content or
    model-provided content — so the bullet-list sections and the long draft never
    silently disagree with each other.
    """
    habitat_text = ", ".join(
        profile.habitat[:3]) if profile.habitat else "its documented habitat types"
    range_text = ", ".join(
        profile.range_summary[:4]) if profile.range_summary else "its known geographic range"
    trend_text = (
        profile.population_trend
        or iucn_context.get("population_trend")
        or "not reported in the available sources"
    )
    family_text = f"{profile.family or 'Unknown family'}, order {profile.order_name or 'Unknown'}"
    evidence_count = len(evidence)

    evidence_lines = []
    for item in evidence[:4]:
        if item.title:
            evidence_lines.append(f"- {item.title}")

    draft_lines = [
        f"# Extinction-risk assessment: {profile.common_name} (*{profile.scientific_name}*)",
        "",
        "## Species snapshot",
        f"{profile.common_name} belongs to {family_text}. It is associated with {habitat_text} and occurs across {range_text}.",
        "",
        "## Conservation status",
        f"The best available Red List signal for this species is **{status_label}**, with a reported population trend of **{trend_text}**.",
        "",
        "## Ecological context",
        f"This assessment focuses on how current pressures affect {profile.common_name} specifically, using live evidence and reference records rather than a generic bird-conservation template.",
    ]
    if profile.diet:
        draft_lines.append(f"Diet and foraging notes: {profile.diet}.")
    if profile.migratory_behavior:
        draft_lines.append(f"Movement ecology: {profile.migratory_behavior}.")
    draft_lines.extend([
        "",
        "## Key threats",
    ])
    draft_lines.extend([f"- {threat}" for threat in key_threats]
                       or ["- Threats require further species-specific verification."])
    draft_lines.extend([
        "",
        "## Survivability outlook",
        survivability_text,
        "",
        "## Recommended actions",
    ])
    draft_lines.extend([f"- {action}" for action in mitigation_actions])
    draft_lines.extend([
        "",
        "## Evidence notes",
        f"{evidence_count} source items were reviewed for this draft.",
    ])
    if evidence_lines:
        draft_lines.append("Most relevant sources:")
        draft_lines.extend(evidence_lines)

    return "\n".join(draft_lines)


def _build_evidence_based_report(
    profile: SpeciesProfile,
    evidence: list[EvidenceItem],
    heuristics: dict[str, Any],
    iucn_context: dict[str, Any],
    model_output_status: str,
) -> dict[str, Any]:
    status_code = _normalize_conservation_status(
        profile.iucn_status
        or iucn_context.get("category")
        or iucn_context.get("red_list_category")
    )
    status = _format_conservation_status(status_code)
    species_label = f"{profile.common_name} ({profile.scientific_name})"
    evidence_count = len(evidence)

    key_threats = _extract_threats_from_evidence(
        evidence, profile, iucn_context)
    mitigation_actions = _build_species_specific_mitigation(
        key_threats, profile, iucn_context)

    source_items = [asdict(item) for item in evidence]
    if not source_items:
        gbif_url = profile.source_urls[0] if profile.source_urls else (
            f"{GBIF_BASE}/species/{profile.gbif_key}" if profile.gbif_key else GBIF_BASE)
        source_items = [
            {
                "query": "GBIF species profile",
                "title": f"GBIF species profile: {profile.common_name}",
                "url": gbif_url,
                "snippet": "Live evidence retrieval was limited, so this draft uses the GBIF taxonomic record as the minimum reference.",
                "source": "GBIF",
                "seendate": None,
                "language": None,
            }
        ]

    draft_text = _render_markdown_draft(
        profile,
        status_code=status_code,
        status_label=status,
        key_threats=key_threats,
        mitigation_actions=mitigation_actions,
        survivability_text=_build_survivability_text(
            status_code, profile, iucn_context),
        iucn_context=iucn_context,
        evidence=evidence,
    )

    return {
        "species": {
            "gbif_key": profile.gbif_key,
            "common_name": profile.common_name,
            "scientific_name": profile.scientific_name,
            "family": profile.family,
            "order_name": profile.order_name,
            "iucn_status": status_code,
            "population_trend": profile.population_trend or iucn_context.get("population_trend"),
            "population_size": profile.population_size,
            "habitat": profile.habitat,
            "range_summary": profile.range_summary,
            "diet": profile.diet,
            "breeding_behavior": profile.breeding_behavior,
            "migratory_behavior": profile.migratory_behavior,
            "source_urls": profile.source_urls,
        },
        "current_conservation_status": status,
        "key_threats": key_threats,
        "survivability_assessment": _build_survivability_text(status_code, profile, iucn_context),
        "mitigation_actions": mitigation_actions,
        "sources": source_items,
        "limited_evidence_reasons": [],
        "reviewer_notes": _build_reviewer_notes(evidence_count, model_output_status),
        "decision_support_draft": draft_text,
        "model_name": settings.ollama_report_model,
        "generation_mode": _generation_mode_for_status(model_output_status),
        "model_output_status": model_output_status,
        "evidence_items_reviewed": evidence_count,
        "disclaimer": (
            "Decision-support draft only. This report is not an authoritative conservation verdict and must be reviewed by human experts before use."
        ),
    }


def _normalize_report_sources(
    raw_sources: Any,
    profile: SpeciesProfile,
    evidence: list[EvidenceItem],
) -> list[dict[str, Any]]:
    if not isinstance(raw_sources, list):
        raw_sources = []

    normalized: list[dict[str, Any]] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        if not url:
            url = profile.source_urls[0] if profile.source_urls else (
                f"{GBIF_BASE}/species/{profile.gbif_key}" if profile.gbif_key else GBIF_BASE
            )
        normalized.append(
            {
                "query": str(source.get("query") or "GBIF species profile"),
                "title": str(
                    source.get("title")
                    or source.get("name")
                    or f"GBIF species profile: {profile.common_name}"
                ),
                "url": str(
                    url
                ),
                "snippet": str(
                    source.get("snippet")
                    or source.get("summary")
                    or "Primary taxonomic reference used for this report."
                ),
                "source": source.get("source"),
                "seendate": source.get("seendate"),
                "language": source.get("language"),
            }
        )

    if normalized:
        return normalized

    if evidence:
        return [asdict(item) for item in evidence]

    return [
        {
            "query": "GBIF species profile",
            "title": f"GBIF species profile: {profile.common_name}",
            "url": profile.source_urls[0] if profile.source_urls else (
                f"{GBIF_BASE}/species/{profile.gbif_key}" if profile.gbif_key else GBIF_BASE
            ),
            "snippet": "Primary taxonomic reference used for this report.",
            "source": "GBIF",
            "seendate": None,
            "language": None,
        }
    ]


_REPORT_OVERALL_BUDGET_SECONDS = 240.0
_EVIDENCE_GATHERING_BUDGET_SECONDS = 75.0


def _seconds_left(start: float, budget: float) -> float:
    return budget - (time.monotonic() - start)


async def generate_extinction_risk_report(
    species_name: str,
    gbif_key: Optional[int] = None,
    country_code: Optional[str] = None,
    language: Optional[str] = None,
) -> dict[str, Any]:
    report_start = time.monotonic()

    profile = await _resolve_gbif_species(species_name, gbif_key=gbif_key)
    if not profile.scientific_name:
        profile.scientific_name = species_name

    profile, wiki_context = await _enrich_species_profile(profile, country_code=country_code)

    iucn_context = await _fetch_iucn_context(profile.scientific_name)
    if iucn_context:
        if not profile.iucn_status:
            profile.iucn_status = iucn_context.get(
                "category") or iucn_context.get("red_list_category")
        if not profile.population_trend and iucn_context.get("population_trend"):
            profile.population_trend = iucn_context.get("population_trend")

    occurrence_trend = await _fetch_gbif_occurrence_trend(profile.gbif_key, country_code=country_code)

    queries = _build_species_queries(profile, country_code=country_code)
    if language:
        queries = [f"{query} language:{language}" for query in queries]

    evidence: list[EvidenceItem] = []
    evidence_gathering_start = time.monotonic()
    for query in queries[:6]:
        if time.monotonic() - evidence_gathering_start > _EVIDENCE_GATHERING_BUDGET_SECONDS:
            logger.info(
                "Evidence-gathering budget (%.0fs) reached for %s, stopping early with %d items so far",
                _EVIDENCE_GATHERING_BUDGET_SECONDS, profile.scientific_name, len(
                    evidence),
            )
            break
        if len(evidence) >= 10:
            logger.info(
                "Already collected %d evidence items for %s, skipping remaining queries",
                len(evidence), profile.scientific_name,
            )
            break

        news_evidence: list[EvidenceItem] = []
        try:
            news_evidence = await asyncio.wait_for(
                _search_news_rss(query, max_records=4,
                                 country_code=country_code),
                timeout=15.0,
            )
            evidence.extend(news_evidence)
            logger.info("News RSS fetched %d items for %s", len(
                news_evidence), profile.scientific_name)
        except asyncio.TimeoutError:
            logger.warning("News RSS fetch timeout for %s",
                           profile.scientific_name)
        except Exception as exc:
            logger.warning("News RSS fetch failed for %s: %s",
                           profile.scientific_name, exc)

        if len(news_evidence) < 2:
            try:
                gdelt_evidence = await asyncio.wait_for(
                    _search_gdelt(query, max_records=4),
                    timeout=20.0,
                )
                evidence.extend(gdelt_evidence)
                logger.info("GDELT fetched %d items for %s", len(
                    gdelt_evidence), profile.scientific_name)
            except asyncio.TimeoutError:
                logger.warning("GDELT fetch timeout for %s",
                               profile.scientific_name)
            except Exception as exc:
                logger.warning("GDELT fetch failed for %s: %s",
                               profile.scientific_name, exc)

    structured_evidence = _build_structured_fallback_evidence(
        profile, iucn_context, wiki_context)
    evidence = structured_evidence + evidence

    deduped: dict[str, EvidenceItem] = {}
    for item in evidence:
        key = item.url or f"{item.title}|{item.snippet}"
        if key not in deduped:
            deduped[key] = item
    evidence = _filter_relevant_evidence(list(deduped.values()), profile)[:14]

    heuristics = _heuristics_from_evidence(evidence)
    limited_evidence_reasons = _build_limited_evidence_reasons(
        profile, evidence, iucn_context)
    payload = _build_user_payload(
        profile, iucn_context, evidence, heuristics, wiki_context=wiki_context,
        occurrence_trend=occurrence_trend,
    )

    # ── Stage A: short structured analysis (status, threats, mitigation, assessment) ──
    # Reserve at least ~30s for Stage B and leave a safety margin under the overall budget.
    model_output_status = "unavailable"
    parsed: dict[str, Any] = {}
    raw_response = ""
    stage_a_budget = _seconds_left(
        report_start, _REPORT_OVERALL_BUDGET_SECONDS) - 40.0
    if stage_a_budget < 20.0:
        logger.warning(
            "Not enough time budget left to attempt Stage A for %s (%.0fs left) — using evidence-based report",
            profile.scientific_name, stage_a_budget,
        )
        model_output_status = "timeout"
    else:
        try:
            raw_response = await asyncio.wait_for(
                _call_ollama_report_model(
                    _structured_messages(payload), num_predict=900),
                timeout=min(110.0, stage_a_budget),
            )
        except Exception as exc:
            model_output_status = _classify_model_exception(exc)
            logger.warning(
                "Structured report call failed for %s: %s", profile.scientific_name, exc)
        else:
            parsed, model_output_status = _parse_structured_response(
                raw_response)
            if model_output_status == "invalid_json":
                retry_budget = _seconds_left(
                    report_start, _REPORT_OVERALL_BUDGET_SECONDS) - 40.0
                if retry_budget < 20.0:
                    logger.info(
                        "Skipping structured-report repair retry for %s — not enough budget left (%.0fs)",
                        profile.scientific_name, retry_budget,
                    )
                else:
                    # One repair retry: show the model its own bad output and ask it to fix the format.
                    try:
                        retry_response = await asyncio.wait_for(
                            _call_ollama_report_model(
                                _structured_repair_messages(payload, raw_response), num_predict=900,
                            ),
                            timeout=min(110.0, retry_budget),
                        )
                    except Exception as exc:
                        logger.warning(
                            "Structured report repair retry failed for %s: %s", profile.scientific_name, exc)
                    else:
                        parsed, model_output_status = _parse_structured_response(
                            retry_response)

    if parsed:
        parsed = _normalize_model_payload(
            parsed, profile, iucn_context, evidence)

    # ── Stage B: long-form markdown draft, only attempted once Stage A gave us something ──
    # AND only if there's still enough budget left — otherwise the locally re-rendered
    # markdown draft (built later from the final merged fields) is used instead.
    model_draft: Optional[str] = None
    stage_b_budget = _seconds_left(
        report_start, _REPORT_OVERALL_BUDGET_SECONDS) - 10.0
    if model_output_status in {"complete", "partial"} and parsed and stage_b_budget >= 20.0:
        try:
            draft_response = await asyncio.wait_for(
                _call_ollama_report_model(
                    _draft_messages(payload, parsed), num_predict=1300, want_json=False,
                ),
                timeout=min(170.0, stage_b_budget),
            )
        except Exception as exc:
            logger.warning(
                "Draft-stage call failed for %s (structured analysis is still used): %s",
                profile.scientific_name, exc,
            )
        else:
            candidate = _strip_fences(draft_response).strip()
            if (
                _has_text(candidate)
                and not _contains_failure_language(candidate)
                and profile.common_name.lower() in candidate.lower()
            ):
                model_draft = candidate
    elif model_output_status in {"complete", "partial"} and parsed:
        logger.info(
            "Skipping draft-stage call for %s — not enough time budget left (%.0fs); "
            "the markdown draft will be re-rendered locally from the structured analysis instead",
            profile.scientific_name, stage_b_budget,
        )

    final_report = _build_evidence_based_report(
        profile,
        evidence,
        heuristics,
        iucn_context,
        model_output_status=model_output_status,
    )

    if parsed:
        parsed_status = parsed.get("current_conservation_status")
        if _has_text(parsed_status) and not _is_generic_list_item(str(parsed_status)):
            final_report["current_conservation_status"] = _format_conservation_status(
                str(parsed_status).strip())

        parsed_threats = [
            str(item).strip()
            for item in (parsed.get("key_threats") or [])
            if str(item).strip() and not _is_generic_list_item(str(item))
        ]
        if parsed_threats:
            final_report["key_threats"] = parsed_threats

        if _has_text(parsed.get("survivability_assessment")):
            final_report["survivability_assessment"] = str(
                parsed["survivability_assessment"]).strip()

        parsed_mitigation = [
            str(item).strip()
            for item in (parsed.get("mitigation_actions") or [])
            if str(item).strip() and not _is_generic_list_item(str(item))
        ]
        if parsed_mitigation:
            final_report["mitigation_actions"] = parsed_mitigation

        if model_draft:
            final_report["decision_support_draft"] = model_draft
        elif parsed_threats or parsed_mitigation or _has_text(parsed_status):
            # Stage A gave us a genuine model-driven status/threats/mitigation, but Stage B
            # (the long-form draft) didn't come back usable — re-render the markdown from
            # the final, post-merge fields so the draft text matches the bullet lists above
            # instead of falling back to the pre-merge evidence-based wording.
            status_code_final = _normalize_conservation_status(
                final_report["current_conservation_status"])
            final_report["decision_support_draft"] = _render_markdown_draft(
                profile,
                status_code=status_code_final,
                status_label=final_report["current_conservation_status"],
                key_threats=final_report["key_threats"],
                mitigation_actions=final_report["mitigation_actions"],
                survivability_text=final_report["survivability_assessment"],
                iucn_context=iucn_context,
                evidence=evidence,
            )

        candidate_notes = parsed.get("reviewer_notes")
        if _has_text(candidate_notes) and not _contains_failure_language(candidate_notes):
            final_report["reviewer_notes"] = str(candidate_notes).strip()

        if parsed.get("sources"):
            final_report["sources"] = _normalize_report_sources(
                parsed.get("sources"), profile, evidence)

        parsed_limited = parsed.get("limited_evidence_reasons")
        if isinstance(parsed_limited, list):
            limited_evidence_reasons.extend(
                str(item).strip()
                for item in parsed_limited
                if str(item).strip() and not _is_prompt_echo(str(item))
            )

    final_report["sources"] = _normalize_report_sources(
        final_report.get("sources"), profile, evidence)
    final_report["sources"] = _dedupe_sources(_build_reference_sources(
        profile, iucn_context) + final_report["sources"])

    deduped_reasons: list[str] = []
    seen_reasons: set[str] = set()
    for reason in limited_evidence_reasons:
        if reason not in seen_reasons:
            seen_reasons.add(reason)
            deduped_reasons.append(reason)
    final_report["limited_evidence_reasons"] = deduped_reasons

    draft = final_report["decision_support_draft"]
    final_report["decision_support_draft"] = draft
    # Legacy repair/heuristic output is not an evidence-fidelity validation.
    final_report["draft_for_review"] = True
    final_report["validation_status"] = "legacy_unverified"
    final_report["validation_errors"] = [
        "Legacy prose and heuristic threats require claim-by-claim human review."
    ]
    final_report["missing_evidence_fields"] = [
        field_name for field_name in (
            "iucn_status", "population_trend", "population_size", "habitat",
            "range_summary", "diet", "breeding_behavior", "migratory_behavior",
        ) if not getattr(profile, field_name, None)
    ]
    supplied_status = iucn_context.get("category") or iucn_context.get("red_list_category") or profile.iucn_status
    if supplied_status and str(supplied_status).strip().lower() in {
        key for key in _IUCN_STATUS_ALIASES if key not in {"unknown", "unassessed", "not assessed"}
    }:
        final_report["current_conservation_status"] = _format_conservation_status(str(supplied_status))
    else:
        final_report["current_conservation_status"] = "Unavailable in supplied evidence"
        final_report["validation_errors"].append("No source-reported IUCN category was supplied; no official category inferred.")
    return final_report
