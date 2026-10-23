"""Consistency checks for data/schema/*.yaml (no Excel files needed)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "data/schema"
manifest = yaml.safe_load((SCHEMA / "manifest.yaml").read_text(encoding="utf-8"))
taxonomy = yaml.safe_load((SCHEMA / "taxonomy.yaml").read_text(encoding="utf-8"))
aliases = yaml.safe_load((SCHEMA / "column_aliases.yaml").read_text(encoding="utf-8"))

CATEGORIES = {c["code"]: c for c in taxonomy["categories"]}
KINDS = {"diagnose", "fast_track", "inspect"}


def test_manifest_lists_every_raw_file_once():
    paths = [f["path"] for f in manifest["files"]]
    assert len(paths) == len(set(paths)) == 18
    assert sorted(f["file_no"] for f in manifest["files"]) == list(range(1, 19))
    on_disk = {str(p.relative_to(ROOT)) for p in (ROOT / "data/raw").glob("*.xlsx")}
    assert set(paths) == on_disk


def test_manifest_and_taxonomy_agree_on_sources():
    from_manifest = {(f["file_no"], prefix, code) for f in manifest["files"] for prefix, code in f["categories"].items()}
    from_taxonomy = {(s["file"], s["prefix"], c["code"]) for c in taxonomy["categories"] for s in c["sources"]}
    assert from_manifest == from_taxonomy


def test_41_categories_from_42_source_groups():
    groups = [(s["file"], s["prefix"]) for c in taxonomy["categories"] for s in c["sources"]]
    assert len(groups) == len(set(groups)) == 42
    assert len(CATEGORIES) == 41


def test_category_fields_are_valid():
    for c in taxonomy["categories"]:
        assert c["kind"] in KINDS, c["code"]
        assert c.get("filter") is None or c["filter"] in taxonomy["vehicle_filters"], c["code"]
        assert c["wave"] in (1, 2, 2.5, 3), c["code"]


def test_tiles_emergency_and_inspection_reference_known_categories():
    refs = [cat for t in taxonomy["tiles"] for cat in t["categories"]]
    refs += [cat for t in taxonomy["emergency"]["topics"] for cat in t["categories"]]
    refs += taxonomy["inspection"]["categories"]
    assert set(refs) <= set(CATEGORIES)
    assert set(CATEGORIES) <= set(refs), f"unreachable categories: {set(CATEGORIES) - set(refs)}"


def test_tile_counts_and_labels():
    assert len(taxonomy["tiles"]) == 13
    assert len(taxonomy["emergency"]["topics"]) == 8
    for entry in taxonomy["tiles"] + taxonomy["emergency"]["topics"] + [taxonomy["inspection"]]:
        assert entry["label_en"].strip() and entry["label_hi"].strip(), entry["code"]


def test_required_vehicle_filters():
    f = taxonomy["vehicle_filters"]
    assert f["cng"] == {"fuel": ["cng"]}
    assert f["ev_hybrid"] == {"fuel": ["ev", "hybrid"]}
    assert f["diesel"] == {"fuel": ["diesel"]}
    assert f["clutch"] == {"transmission": ["mt", "amt"]}
    assert CATEGORIES["cng"]["filter"] == "cng"
    assert CATEGORIES["ev_hybrid"]["filter"] == "ev_hybrid"
    assert CATEGORIES["diesel"]["filter"] == "diesel"
    assert CATEGORIES["clutch"]["filter"] == "clutch"


def test_alias_map_marks_internal_columns():
    internal = {c["field"] for c in aliases["template_columns"] if c["visibility"] == "internal"}
    assert {"mechanic_task", "mechanic_repair_steps", "internal_notes"} <= internal
    assert len(aliases["template_columns"]) == 34
    assert len(aliases["ev_extra_columns"]) == 8
    positions = [c["position"] for c in aliases["template_columns"] + aliases["ev_extra_columns"]]
    assert positions == list(range(1, 43))
