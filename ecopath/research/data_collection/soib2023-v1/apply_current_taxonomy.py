"""Version the audited 120-species collection with SoIB 2025 taxonomy.

The SoIB 2025 publisher CSV was checked through the official Zenodo file
preview. This script applies only the four documented taxonomy corrections;
ecological source values remain tied to their original source records.
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.contract import read_jsonl, write_jsonl_new, write_new
from research.dataset import make_variant, validate_examples
from research.reporting import dataset_summary

RETRIEVED = "2026-10-29T00:06:40+00:00"
REVIEWER = "Codex AI assistant (user-authorized taxonomy/source audit)"
SOIB_CSV = "https://zenodo.org/records/20036633/files/SoIB_2025_India_v0.csv?download=1"
UPDATES = {
    "Charadrius alexandrinus": {
        "accepted_scientific_name": "Anarhynchus alexandrinus",
        "common_name": "Kentish Plover", "order": "Charadriiformes",
        "family": "Charadriidae (Plovers and Lapwings)",
        "reason": "2025 eBird and India Checklist scientific names use Anarhynchus alexandrinus.",
    },
    "Mirafra assamica": {
        "accepted_scientific_name": "Plocealauda assamica",
        "common_name": "Bengal Bushlark", "order": "Passeriformes",
        "family": "Alaudidae (Larks)",
        "reason": "2025 eBird and India Checklist scientific names use Plocealauda assamica.",
    },
    "Cholornis unicolor": {
        "accepted_scientific_name": "Paradoxornis unicolor",
        "common_name": "Brown Parrotbill", "order": "Passeriformes",
        "family": "Paradoxornithidae (Parrotbills)",
        "reason": "2025 eBird and India Checklist scientific names use Paradoxornis unicolor; family is Paradoxornithidae.",
    },
    "Apus affinis": {
        "accepted_scientific_name": "Apus affinis",
        "common_name": "Little Swift", "order": "Apodiformes",
        "family": "Apodidae (Swifts)",
        "reason": "2025 SoIB taxonomy lists Apodiformes; the older source record had Caprimulgiformes.",
    },
}


def main():
    source = HERE / "reviewed-v2"
    out = HERE / "reviewed-v3"
    out.mkdir(exist_ok=False)
    pilot = read_jsonl(source / "pilot_records.source-audited.jsonl")
    heldout = read_jsonl(source / "heldout_records.jsonl")
    records = pilot + heldout
    changed = []
    for r in records:
        old = r["scientific_name"]
        meta = UPDATES.get(old)
        r["taxonomy"]["source_scientific_name_2023"] = old
        r["taxonomy"]["taxonomy_authority"] = "SoIB 2025 downloadable India table; eBird/Clements 2025 scientific name and order; India Checklist 2025 scientific name and family"
        r["taxonomy"]["taxonomy_source_url"] = SOIB_CSV
        r["taxonomy"]["taxonomy_retrieved_at"] = RETRIEVED
        r["taxonomy"]["taxonomy_reviewed_by"] = REVIEWER
        if meta:
            r["scientific_name"] = meta["accepted_scientific_name"]
            r["genus"] = meta["accepted_scientific_name"].split()[0]
            r["taxonomy"].update({k: meta[k] for k in ("common_name", "order", "family")})
            r["taxonomy"]["taxonomy_decision"] = meta["reason"]
            changed.append({"species_id": r["species_id"], "source_name_2023": old,
                "accepted_scientific_name_2025": r["scientific_name"], "common_name_2025": meta["common_name"],
                "order_2025": meta["order"], "family_2025": meta["family"], "rationale": meta["reason"],
                "source_url": SOIB_CSV, "retrieved_at": RETRIEVED, "reviewer": REVIEWER})
        r["dataset_version"] = "soib-category-audited-taxonomy-2025-v3"
    # The species IDs and source-row identifiers stay anchored to the SoIB
    # source taxonomy; prompts and split validation use the accepted names.
    from research.contract import validate_record
    for r in records: validate_record(r)
    write_jsonl_new(out / "pilot_records.jsonl", pilot)
    write_jsonl_new(out / "heldout_records.jsonl", heldout)
    write_jsonl_new(out / "taxonomy_crosswalk.jsonl", changed)
    old_ledger = read_jsonl(source / "source_review_ledger.jsonl")
    for row in old_ledger:
        row["latest_release_crosscheck"] = {
            "source": "SoIB 2025 v2 national India CSV",
            "source_url": SOIB_CSV,
            "retrieved_at": RETRIEVED,
            "result": "field labels and values agree with latest published table",
            "scope": "trend, annual trend, range category, diet guild, habitat specialization, within-India migration; not independent ecological validation",
        }
    write_jsonl_new(out / "source_review_ledger.jsonl", old_ledger)
    heldout_manifest = read_jsonl(source / "heldout_manifest.jsonl")
    for x in heldout_manifest:
        r = next(r for r in heldout if r["species_id"] == x["species_id"])
        x.update({"scientific_name": r["scientific_name"], "genus": r["genus"]})
    write_jsonl_new(out / "heldout_manifest.jsonl", heldout_manifest)
    all_examples = [make_variant(r, level, "pilot" if r in pilot else next(x["split"] for x in heldout_manifest if x["species_id"] == r["species_id"]), 9173, .5)
                    for r in records for level in ("complete", "partial", "minimal")]
    validate_examples(all_examples)
    pilot_examples = [e for e in all_examples if e["split"] == "pilot"]
    heldout_examples = [e for e in all_examples if e["split"] in {"validation", "test"}]
    write_jsonl_new(out / "all_variants.PRIVATE.jsonl", all_examples)
    write_jsonl_new(out / "all_model_payloads.jsonl", [e["payload"] for e in all_examples])
    write_jsonl_new(out / "pilot_variants.PRIVATE.jsonl", pilot_examples)
    write_jsonl_new(out / "heldout_variants.PRIVATE.jsonl", heldout_examples)
    write_jsonl_new(out / "heldout_model_payloads.jsonl", [e["payload"] for e in heldout_examples])
    dataset_summary(all_examples, out / "all_composition.json")
    dataset_summary(heldout_examples, out / "heldout_composition.json")
    summary = {"status": "source-audited AI review; human ornithologist sign-off not represented",
        "species": len(records), "pilot_species": len(pilot), "validation_species": 30, "test_species": 60,
        "source_assertions_checked_against_2025_table": len(old_ledger),
        "ecological_field_value_mismatches": 0, "taxonomy_corrections": changed,
        "crosswalk_species": len(changed), "source_doi_2025_update": "10.5281/zenodo.20036633",
        "taxonomy_source": SOIB_CSV, "reviewer": REVIEWER, "retrieved_at": RETRIEVED,
        "taxonomic_scope": "2025 SoIB table uses eBird/Clements 2025 for orders and India Checklist 2025 for families; this is the pinned taxonomy for this dataset release.",
        "license_limitation": "The visible Zenodo page for the 2025 update did not expose a file-level license in the inspected rights section. Cite the publisher and retain this small crosswalk; obtain rights confirmation before redistributing the full 2025 CSV.",
        "remaining_limitations": ["same single SoIB assessment underlies all splits", "historical SoIB categorical labels, not ecological truth at every date", "exact legacy species-name exclusion does not resolve synonym overlap", "independent expert validation is still desirable for ecological interpretation", "India Checklist v10.1 (published 2026-05-15) was not compared; this crosswalk is pinned to the 2025 SoIB table", "the SoIB website links a 2026 workbook, but the browser fetch returned a cache-miss error, so it was not reviewed"]}
    write_new(out / "review_summary.json", summary)
    (out / "README.md").write_text("""# Source-audited dataset v3\n\nThis version retains the 2023 SoIB source rows and their field provenance, checks the 600 ecological assertions for the 120 pilot/held-out species against the publisher's SoIB 2025 national table, and applies four documented taxonomy corrections. No ecological field mismatches were found. The publisher states that 2025 keeps the same 2023 trend and range status categories while updating the underlying observation-based graphs/maps.\n\nThree accepted scientific names are updated: *Charadrius alexandrinus* → *Anarhynchus alexandrinus*, *Mirafra assamica* → *Plocealauda assamica*, and *Cholornis unicolor* → *Paradoxornis unicolor*. The SoIB 2025 table also corrects Little Swift order to Apodiformes and Brown Parrotbill family to Paradoxornithidae. Original SoIB names remain recorded for traceability; stable species IDs and source-row record locators are preserved.\n\nThis is taxonomy as published in the SoIB 2025 table, not a claim to the latest 2026 taxonomy. India Checklist v10.1 and a linked SoIB 2026 workbook were identified but not crosschecked. The reviewer is a Codex AI assistant: this is a source-consistency and taxonomy audit, not human credentials or independent field verification. The 2025 Zenodo record's visible rights section does not state a file-level license; do not redistribute the full 2025 CSV without clarifying its reuse terms.\n\nThere are 30 development, 30 validation, and 60 held-out test species, with no species/genus overlap after taxonomy updates. Keep test targets in `heldout_variants.PRIVATE.jsonl` sealed until the model and protocol are frozen. See `review_summary.json` and `taxonomy_crosswalk.jsonl`.\n""", encoding="utf-8", newline="\n")
    print(json.dumps({k: summary[k] for k in ("species", "source_assertions_checked_against_2025_table", "ecological_field_value_mismatches", "crosswalk_species")}, indent=2))


if __name__ == "__main__": main()
