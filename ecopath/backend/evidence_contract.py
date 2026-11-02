"""Versioned, deliberately narrow structured-fact contract.

Source support here means agreement with a reviewed extraction, not proof that
unrestricted prose follows from an external document. Prose requires annotation.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path


VERSION = "ecopath-evidence-v2"
FIELDS = (
    "iucn_status", "population_trend", "population_size", "habitat",
    "range_summary", "diet", "breeding_behavior", "migratory_behavior", "key_threats",
)
VALUE_SCHEMA = {"anyOf": [
    {"type": "null"}, {"type": "string", "minLength": 1},
    {"type": "number"},
    {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
]}
ANSWER_SCHEMA = {"anyOf": [
    {"type": "object", "additionalProperties": False,
     "required": ["value", "kind", "source_ids"],
     "properties": {"value": {"type": "null"}, "kind": {"type": "string", "enum": ["unavailable"]},
                    "source_ids": {"type": "array", "maxItems": 0, "items": {"type": "string"}}}},
    {"type": "object", "additionalProperties": False,
     "required": ["value", "kind", "source_ids"],
     "properties": {"value": {"anyOf": VALUE_SCHEMA["anyOf"][1:]},
                    "kind": {"type": "string", "enum": ["source_reported"]},
                    "source_ids": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}}},
]}

REPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object", "additionalProperties": False,
    "required": ["schema_version", "example_id", "scientific_name", "draft_for_review", "fields", "claims", "suggested_actions"],
    "properties": {
        "schema_version": {"type": "string", "enum": [VERSION]},
        "example_id": {"type": "string", "minLength": 1},
        "scientific_name": {"type": "string", "minLength": 1},
        "draft_for_review": {"type": "string", "enum": ["draft_for_human_review"]},
        "fields": {"type": "object", "additionalProperties": False, "required": list(FIELDS),
                   "properties": {key: ANSWER_SCHEMA for key in FIELDS}},
        "claims": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "source_ids"],
            "properties": {"text": {"type": "string", "minLength": 1},
                           "source_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}}},
        }},
        "suggested_actions": {"type": "array", "items": {"type": "string", "minLength": 1}},
    },
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    rows = []
    for i, line in enumerate(Path(path).read_text().splitlines(), 1):
        if line.strip():
            try:
                rows.append(strict_json(line))
            except ValueError as exc:
                raise ValueError(f"{path}:{i}: {exc}") from exc
    return rows


def write_new(path, value):
    """Exclusive creation: existing artifacts are never silently replaced."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_jsonl_new(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical(row) + "\n")


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def invalid_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def report_errors(report, payload=None):
    from jsonschema import Draft202012Validator
    errors = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in Draft202012Validator(REPORT_SCHEMA).iter_errors(report)]
    if payload and isinstance(report, dict):
        for key in ("example_id", "scientific_name"):
            if report.get(key) != payload[key]:
                errors.append(f"{key}: identity mismatch")
    return errors


def normalize(value, field=""):
    """Only whitespace/case, explicit status aliases, and unordered list values."""
    if isinstance(value, str):
        value = " ".join(value.split()).casefold()
        if field == "iucn_status":
            aliases = {"least concern": "lc", "near threatened": "nt", "vulnerable": "vu",
                       "endangered": "en", "critically endangered": "cr", "extinct in the wild": "ew",
                       "extinct": "ex", "data deficient": "dd", "not evaluated": "ne"}
            value = aliases.get(value, value)
        return value
    if isinstance(value, list):
        return sorted(normalize(v, field) for v in value)
    return value


def valid_value(value):
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (float, int)):
        return math.isfinite(value)
    if isinstance(value, str):
        return bool(value.strip()) and value.casefold().strip() not in {"unknown", "unavailable", "n/a"}
    return (isinstance(value, list) and bool(value) and all(isinstance(v, str) and v.strip() for v in value)
            and len(set(normalize(v) for v in value)) == len(value))


def validate_record(record):
    required = {"species_id", "scientific_name", "genus", "taxonomy", "sampling", "fields", "sources", "dataset_version"}
    if set(record) != required:
        raise ValueError(f"record keys must be {sorted(required)}")
    for key in ("species_id", "scientific_name", "genus", "dataset_version"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"invalid {key}")
    if record["scientific_name"].split()[0] != record["genus"]:
        raise ValueError("genus disagrees with scientific name")
    if not isinstance(record["taxonomy"], dict) or not isinstance(record["sampling"], dict):
        raise ValueError("taxonomy and sampling must be objects")
    if set(record["fields"]) != set(FIELDS):
        raise ValueError("all contract fields required; use null for missing")
    if not isinstance(record["sources"], list):
        raise ValueError("sources must be a list")
    ids = set()
    for source in record["sources"]:
        keys = {"source_id", "record_id", "url", "retrieved_at", "excerpt", "field", "value", "license", "extraction_review"}
        if set(source) != keys or source["field"] not in FIELDS or source["source_id"] in ids:
            raise ValueError("malformed/duplicate source assertion")
        ids.add(source["source_id"])
        if not all(isinstance(source[k], str) and source[k].strip() for k in ("source_id", "record_id", "url", "excerpt", "license", "extraction_review")):
            raise ValueError("source identifiers, excerpt, license and extraction review required")
        if not re.match(r"^https?://", source["url"]):
            raise ValueError("source URL must use http(s)")
        if source["retrieved_at"] is not None:
            from datetime import datetime
            stamp = datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("retrieval datetime must include timezone")
        if not valid_value(source["value"]):
            raise ValueError("source assertion has no supported value")
    source_map = {s["source_id"]: s for s in record["sources"]}
    for field, entry in record["fields"].items():
        if not isinstance(entry, dict) or set(entry) != {"value", "source_ids", "availability"}:
            raise ValueError("field must contain value, source_ids, availability")
        value = entry["value"]
        if entry["availability"] not in {"available", "missing", "conflicting"}:
            raise ValueError("invalid availability")
        if not isinstance(entry["source_ids"], list) or len(set(entry["source_ids"])) != len(entry["source_ids"]):
            raise ValueError("invalid source IDs")
        sources = [source_map.get(s) for s in entry["source_ids"]]
        if any(s is None or s["field"] != field for s in sources):
            raise ValueError("unknown source or cross-field source")
        if entry["availability"] == "available":
            if field == 'iucn_status' and normalize(value,field) not in {'lc','nt','vu','en','cr','ew','ex','dd','ne'}:
                raise ValueError('IUCN category must be an explicitly sourced recognised category')
            if not valid_value(value) or not sources:
                raise ValueError("available value needs source support")
            if any(normalize(s["value"], field) != normalize(value, field) for s in sources):
                raise ValueError("conflicting extraction cannot be available")
        elif value is not None:
            raise ValueError("missing/conflicting values must be null")
        if entry["availability"] == "missing" and sources:
            raise ValueError("missing values cannot have supporting assertions")
        if entry["availability"] == "conflicting" and len({canonical(normalize(s['value'], field)) for s in sources}) < 2:
            raise ValueError("conflicting fields need differing source assertions")
    referenced = {s for e in record['fields'].values() for s in e['source_ids']}
    if referenced != ids:
        raise ValueError("unreferenced source assertions")
    return record


def template(payload):
    return {
        "schema_version": VERSION, "example_id": payload["example_id"],
        "scientific_name": payload["scientific_name"], "draft_for_review": "draft_for_human_review",
        "fields": {key: {"value": e["value"], "kind": "source_reported" if e["availability"] == "available" else "unavailable",
                         "source_ids": e["source_ids"] if e["availability"] == "available" else []}
                   for key, e in payload["fields"].items()},
        "claims": [], "suggested_actions": [],
    }


def validate_payload(payload):
    """Accept only a canonical model-visible payload, never a private example."""
    if not isinstance(payload, dict) or set(payload) != {'schema_version','example_id','scientific_name','fields','sources'}:
        raise ValueError('payload must contain only schema_version, example_id, scientific_name, fields, sources')
    if payload['schema_version'] != VERSION or not all(isinstance(payload[k],str) and payload[k].strip() for k in ('example_id','scientific_name')):
        raise ValueError('invalid payload version or identity')
    if not isinstance(payload['fields'],dict) or set(payload['fields']) != set(FIELDS) or not isinstance(payload['sources'],list):
        raise ValueError('invalid evidence fields or sources')
    ids=set()
    for s in payload['sources']:
        if not isinstance(s,dict) or set(s) != {'source_id','field','value','excerpt'}:
            raise ValueError('source must be a canonical field assertion')
        if not isinstance(s['source_id'],str) or not s['source_id'] or s['source_id'] in ids or s['field'] not in FIELDS:
            raise ValueError('invalid/duplicate source ID')
        ids.add(s['source_id'])
        if not valid_value(s['value']) or s['excerpt'] != canonical({s['field']:s['value']}):
            raise ValueError('source excerpt must be the exact canonical field projection')
    sources={s['source_id']:s for s in payload['sources']}
    used=set()
    for field, e in payload['fields'].items():
        if not isinstance(e,dict) or set(e) != {'value','source_ids','availability'}:
            raise ValueError('invalid field shape')
        if not isinstance(e['source_ids'],list) or not all(isinstance(s,str) for s in e['source_ids']) or len(set(e['source_ids'])) != len(e['source_ids']):
            raise ValueError('invalid field source IDs')
        if e['availability']=='missing':
            if e['value'] is not None or e['source_ids']:
                raise ValueError('missing field requires null and no sources')
        elif e['availability']=='available':
            if field == 'iucn_status' and normalize(e['value'],field) not in {'lc','nt','vu','en','cr','ew','ex','dd','ne'}:
                raise ValueError('invalid source-reported IUCN category')
            if not valid_value(e['value']) or not e['source_ids']:
                raise ValueError('available field requires a supported value')
            for sid in e['source_ids']:
                s=sources.get(sid)
                if not s or s['field'] != field or normalize(s['value'],field) != normalize(e['value'],field):
                    raise ValueError('source assertion does not support this field value')
                used.add(sid)
        else:
            raise ValueError('model-visible availability must be available or missing')
    if ids != used:
        raise ValueError('unreferenced source assertion')
    return payload


def supported_report_errors(report,payload):
    errors=report_errors(report,payload)
    if errors:
        return errors
    sources={s['source_id']:s for s in payload['sources']}
    for field,answer in report['fields'].items():
        if answer['kind']=='source_reported':
            for sid in answer['source_ids']:
                source=sources.get(sid)
                if not source or source['field']!=field or normalize(source['value'],field)!=normalize(answer['value'],field):
                    errors.append(f'{field}: unsupported value/citation {sid}')
    for i,claim in enumerate(report['claims']):
        if any(sid not in sources for sid in claim['source_ids']):
            errors.append(f'claims/{i}: unknown citation')
    return errors
