import json

from services.extinction_risk_service import (
    EvidenceItem,
    SpeciesProfile,
    _build_evidence_based_report,
    _extract_threats_from_evidence,
    _format_conservation_status,
    _normalize_conservation_status,
    _repair_json_text,
)


def test_repair_json_text_handles_broken_trailing_content():
    raw = '''{
      "decision_support_draft": "A draft with a broken line\nthat continues here",
      "current_conservation_status": "Least Concern",
      "key_threats": [],
      "survivability_assessment": "Uncertain",
      "mitigation_actions": []
    '''
    repaired = _repair_json_text(raw)
    parsed = json.loads(repaired)
    assert parsed["current_conservation_status"] == "Least Concern"
    assert parsed["decision_support_draft"].startswith("A draft")


def test_evidence_based_fallback_uses_live_evidence_and_is_actionable():
    profile = SpeciesProfile(
        gbif_key=5231190,
        common_name="House Sparrow",
        scientific_name="Passer domesticus",
        iucn_status="LC",
        habitat=["farmland", "urban habitats"],
        range_summary=["Europe", "Asia"],
    )
    evidence = [
        EvidenceItem(
            query='"Passer domesticus" habitat loss',
            title="Local sparrow decline linked to habitat loss",
            url="https://example.org/news/1",
            snippet="Habitat loss and land-use change are reducing local populations in several regions.",
            source="News",
        )
    ]

    report = _build_evidence_based_report(
        profile,
        evidence,
        {"threat_labels": ["habitat_loss", "climate_impacts"]},
        {},
        "invalid_json",
    )

    draft = report["decision_support_draft"].lower()
    assert "house sparrow" in draft
    assert "habitat loss" in draft or "habitat" in draft
    assert "further data" not in draft
    assert "insufficient information" not in draft
    assert "protect" in draft or "monitor" in draft
    assert not any(threat.startswith("heuristic:") for threat in report["key_threats"])


def test_evidence_based_fallback_uses_species_specific_habitat_context():
    profile = SpeciesProfile(
        gbif_key=123456,
        common_name="Great Indian Bustard",
        scientific_name="Ardeotis nigriceps",
        iucn_status="CR",
        habitat=["grasslands", "dry scrublands"],
        range_summary=["India"],
    )
    evidence = [
        EvidenceItem(
            query='"Ardeotis nigriceps" grasslands power lines',
            title="Power-line collision threat in grassland breeding habitat",
            url="https://example.org/news/2",
            snippet="Power-line collisions and habitat conversion are affecting breeding success.",
            source="News",
        )
    ]

    report = _build_evidence_based_report(
        profile,
        evidence,
        {"threat_labels": ["habitat_loss", "direct_mortality"]},
        {},
        "invalid_json",
    )

    draft = report["decision_support_draft"].lower()
    assert "grassland" in draft or "grasslands" in draft
    assert "power-line" in draft or "power line" in draft or "collision" in draft
    assert "great indian bustard" in draft
    assert report["current_conservation_status"].startswith("CR")


def test_status_normalization_maps_common_aliases():
    assert _normalize_conservation_status("Least Concern") == "LC"
    assert _normalize_conservation_status("Not Evaluated") == "NE"
    assert _format_conservation_status("CR") == "CR (Critically Endangered)"


def test_extract_threats_prefers_species_specific_evidence():
    profile = SpeciesProfile(
        gbif_key=2474902,
        common_name="Great Indian Bustard",
        scientific_name="Ardeotis nigriceps",
        family="Otididae",
        habitat=["grasslands"],
        range_summary=["India"],
    )
    evidence = [
        EvidenceItem(
            query='"Ardeotis nigriceps" power lines',
            title="Great Indian Bustard power-line collisions in Rajasthan",
            url="https://example.org/news/3",
            snippet="Power-line collisions remain a major mortality source for Great Indian Bustard in grassland breeding habitat.",
            source="News",
        )
    ]
    threats = _extract_threats_from_evidence(evidence, profile, {"category": "CR"})
    joined = " ".join(threats).lower()
    assert "collision" in joined or "power" in joined
    assert "great indian bustard" in joined or "grassland" in joined
