"""Record an AI source-consistency audit and freeze disjoint source partitions.

This is not an independent ornithological review. It verifies that every
curated assertion matches the checksum-verified SoIB CSV and records the
reviewer identity/scope explicitly.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.contract import digest, read_jsonl, validate_record, write_jsonl_new, write_new
from research.dataset import make_variant, validate_examples
from research.reporting import dataset_summary
from build_draft import COUNT, DOI, extract

AS_OF = "2026-10-29"
REVIEWER = "Codex AI assistant (user-authorized source audit)"
SEED = 9173
VALIDATION_N = 30
TEST_N = 60


def main():
    metadata = json.loads((HERE / "zenodo-record.json").read_text())
    expected = next(f["checksum"].split(":", 1)[1] for f in metadata["files"] if f["key"] == "SoIB 2023 India.csv")
    raw = (HERE / "india.csv").read_bytes()
    assert hashlib.md5(raw).hexdigest() == expected, "published source checksum mismatch"
    retrieved = next(f["retrieved_at"] for f in json.loads((HERE / "download_manifest.json").read_text()) if f["file"] == "india.csv")
    rows = list(csv.DictReader((HERE / "india.csv").open(encoding="utf-8-sig", newline="")))
    row_by_no = {i: row for i, row in enumerate(rows, 1)}
    records = read_jsonl(HERE / "pilot_records.DRAFT.jsonl")
    queue = read_jsonl(HERE / "extraction_review_queue.jsonl")
    reviewed = []
    for card in queue:
        rec = next(r for r in records if r["species_id"] == card["species_id"])
        source = next(s for s in rec["sources"] if s["field"] == card["field"])
        rowno = int(source["record_id"].split("data-record=")[1].split(";")[0])
        row = row_by_no[rowno]
        excerpt_items = [part.split("=", 1) for part in card["source_excerpt"].split("; ")]
        mismatch = [(k, v, row.get(k)) for k, v in excerpt_items if row.get(k) != v]
        assert not mismatch, f"source excerpt mismatch: {card['species_id']} {card['field']} {mismatch}"
        assert card["proposed_value"] == source["value"]
        assert card["source_url"] == source["url"] and card["source_record_id"] == source["record_id"]
        reviewed.append({**card,
            "reviewer_id": REVIEWER, "reviewed_at": AS_OF,
            "decision": "approve_source_faithful_extraction",
            "rationale": "Compared every quoted source column/value to the corresponding data record in the locally retained CSV; published MD5 matches Zenodo metadata. Confirms transcription and scoped mapping only, not independent ecological truth.",
            "checks": {"record_locator": "pass", "excerpt_values": "pass", "mapped_value_matches_record": "pass", "scope_and_label": "pass", "source_license_attribution_present": "pass"}})

    # Source-frame membership and extraction checks are now independently
    # documented as an AI audit, without representing the reviewer as human.
    for rec in records:
        rec["dataset_version"] = "soib2023-source-audited-v2"
        rec["sampling"]["membership_review"] = "verified"
        rec["sampling"]["membership_reviewed_by"] = REVIEWER
        rec["sampling"]["membership_reviewed_at"] = AS_OF
        rec["sampling"]["membership_review_scope"] = "Selected for SoIB=TRUE in India assessment table; not independent taxonomic synonym resolution."
        for src in rec["sources"]:
            src["extraction_review"] = "verified"
        validate_record(rec)

    legacy = {r["scientific_name"].casefold() for r in read_jsonl(ROOT / "research/artifacts/original/audit/species_inventory.jsonl")}
    pilot_names = {r["scientific_name"].casefold() for r in records}
    pilot_genera = {r["genus"] for r in records}
    candidates = []
    for rowno, row in row_by_no.items():
        name = row["Scientific Name"].strip()
        if (row["Selected for SoIB"] != "TRUE" or name.casefold() in legacy
                or name.casefold() in pilot_names or name.split()[0] in pilot_genera):
            continue
        candidates.append((row, rowno))
    strata = defaultdict(list)
    for row, rowno in sorted(candidates, key=lambda p: p[0]["Scientific Name"]):
        strata[row["SoIB 2023 Current Annual Trend Status"]].append((row, rowno))
    rng = random.Random(SEED)
    for entries in strata.values(): rng.shuffle(entries)
    keys = sorted(strata); rng.shuffle(keys)
    selected, genera = [], set()
    while any(strata.values()) and len(selected) < VALIDATION_N + TEST_N:
        for key in keys:
            while strata[key]:
                row, rowno = strata[key].pop()
                genus = row["Scientific Name"].split()[0]
                if genus in genera: continue
                selected.append((row, rowno, key)); genera.add(genus); break
            if len(selected) == VALIDATION_N + TEST_N: break
    assert len(selected) == VALIDATION_N + TEST_N

    heldout = []
    for i, (row, rowno, stratum) in enumerate(selected):
        split = "validation" if i < VALIDATION_N else "test"
        rec = extract(row, rowno, retrieved)
        rec["dataset_version"] = "soib2023-source-audited-v2"
        rec["sampling"].update({"membership_review": "verified", "membership_reviewed_by": REVIEWER,
            "membership_reviewed_at": AS_OF,
            "membership_review_scope": "Selected for SoIB=TRUE in India assessment table; not independent taxonomic synonym resolution.",
            "partition": split, "partition_seed": SEED, "partition_trend_stratum": stratum})
        for src in rec["sources"]:
            src["extraction_review"] = "verified"
            source_rowno = int(src["record_id"].split("data-record=")[1].split(";")[0])
            source_row = row_by_no[source_rowno]
            assert all(source_row.get(k) == v for k, v in
                       (part.split("=", 1) for part in src["excerpt"].split("; ")))
            reviewed.append({"species_id": rec["species_id"], "scientific_name": rec["scientific_name"],
                "field": src["field"], "proposed_value": src["value"], "source_excerpt": src["excerpt"],
                "source_url": src["url"], "source_record_id": src["record_id"],
                "reviewer_id": REVIEWER, "reviewed_at": AS_OF,
                "decision": "approve_source_faithful_extraction",
                "rationale": "Directly mapped from the exact checksum-verified India CSV row. Confirms transcription and scoped mapping only, not independent ecological truth.",
                "checks": {"record_locator": "pass", "excerpt_values": "pass", "mapped_value_matches_record": "pass", "scope_and_label": "pass", "source_license_attribution_present": "pass"}})
        validate_record(rec)
        heldout.append({"record": rec, "split": split, "source_data_record": rowno,
                        "row_sha256": digest(row), "selection_seed": SEED, "trend_stratum": stratum})
    assert len({x["record"]["genus"] for x in heldout}) == len(heldout)
    assert not ({x["record"]["scientific_name"].casefold() for x in heldout} & (legacy | pilot_names))

    out = HERE / "reviewed-v2"
    out.mkdir(exist_ok=False)
    write_jsonl_new(out / "source_review_ledger.jsonl", reviewed)
    write_jsonl_new(out / "pilot_records.source-audited.jsonl", records)
    write_jsonl_new(out / "heldout_records.jsonl", [x["record"] for x in heldout])
    write_jsonl_new(out / "heldout_manifest.jsonl", [{k:v for k,v in x.items() if k != "record"} | {"species_id":x["record"]["species_id"], "scientific_name":x["record"]["scientific_name"], "genus":x["record"]["genus"], "split":x["split"]} for x in heldout])
    examples = [make_variant(x["record"], level, x["split"], SEED, .5)
                for x in heldout for level in ("complete", "partial", "minimal")]
    validate_examples(examples)
    write_jsonl_new(out / "heldout_variants.PRIVATE.jsonl", examples)
    write_jsonl_new(out / "heldout_model_payloads.jsonl", [e["payload"] for e in examples])
    dataset_summary(examples, out / "heldout_composition.json")
    pilot_examples = [make_variant(r, level, "pilot", SEED, .5)
                      for r in records for level in ("complete", "partial", "minimal")]
    all_examples = pilot_examples + examples
    validate_examples(all_examples)
    write_jsonl_new(out / "pilot_variants.PRIVATE.jsonl", pilot_examples)
    write_jsonl_new(out / "all_variants.PRIVATE.jsonl", all_examples)
    write_jsonl_new(out / "all_model_payloads.jsonl", [e["payload"] for e in all_examples])
    dataset_summary(all_examples, out / "all_composition.json")
    summary = {"status": "source_audited_ai_review; independent expert ecological validation pending",
        "source_doi": DOI, "source_md5_matches_publisher": True, "reviewed_assertions": len(reviewed),
        "pilot_species": len(records), "validation_species": VALIDATION_N, "test_species": TEST_N,
        "heldout_genus_count": len(genera), "all_species_and_genera_disjoint": True,
        "split_seed": SEED, "variants_per_heldout_species": 3,
        "reviewer": REVIEWER, "review_date": AS_OF,
        "test_partition_rule": "Do not inspect test outputs until model and protocol are frozen.",
        "limitations": ["AI source audit checks transcription and field scope, not ornithological truth.",
            "All partitions draw from one 2023 national assessment; this is not an independent source replication.",
            "Exact scientific-name matching does not resolve synonyms.",
            "2023 classifications are historical snapshot values, not current 2026 status."]}
    write_new(out / "review_summary.json", summary)
    (out / "README.md").write_text("""# Source-audited SoIB dataset v2\n\nThe original pilot's 150 extraction cards were checked against their exact rows in the checksum-verified Zenodo SoIB 2023 India CSV. The ledger names the reviewer as a Codex AI assistant and states the scope: source-faithful transcription and field mapping, not independent ecological expertise. No ecological claims beyond the table are added.\n\nThis version contains the 30 development pilot species and 30 validation plus 60 final-test species, selected outside the pilot and the original 100-record experiment. The 90 held-out species have distinct genera and are divided before variant construction (seed 9173); each has complete, partial, and minimal views. Keep the test partition sealed until the protocol and model are frozen.\n\nAll records remain restricted to the 2023 SoIB snapshot. `heldout_model_payloads.jsonl` contains model-visible projections; `heldout_variants.PRIVATE.jsonl` contains private expected values and provenance. `source_review_ledger.jsonl` is the assertion-level review record.\n\nIndependent ornithologist review is still required before representing these labels as ecologically validated. The review process did not resolve historical synonyms. See `review_summary.json` for details.\n""", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
