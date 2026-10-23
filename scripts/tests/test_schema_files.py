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
        assert "filter" not in c, f"{c['code']}: use 'filters' (a list)"
        assert set(c.get("filters", [])) <= set(taxonomy["vehicle_filters"]), c["code"]
        assert c["wave"] in (1, 2, 2.5, 3), c["code"]
        assert "name_hi" not in c, "categories have no Hindi name"


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
    assert f["clutch"] == {"transmission": ["mt", "amt", "dct"]}
    assert f["petrol_engine"] == {"fuel": ["petrol", "cng", "hybrid"]}
    assert f["combustion_engine"] == {"fuel": ["petrol", "diesel", "cng", "hybrid"]}


def shown(category: str, **car) -> bool:
    """Reference reading of the filter rules: all filters must match; an unknown attribute passes."""
    for name in CATEGORIES[category].get("filters", []):
        for attr, allowed in taxonomy["vehicle_filters"][name].items():
            if car.get(attr) is not None and car[attr] not in allowed:
                return False
    return True


ENGINE_ONLY = ["clutch", "engine_belt", "jerking_misfire", "exhaust", "fuel_delivery", "cng", "diesel"]


def test_pure_ev_hides_engine_only_categories_but_hybrid_keeps_them():
    for code in ENGINE_ONLY:
        assert not shown(code, fuel="ev", transmission="at"), code
    for code in ["clutch", "engine_belt", "jerking_misfire", "exhaust", "fuel_delivery"]:
        assert shown(code, fuel="hybrid", transmission="amt"), code
    assert shown("ev_hybrid", fuel="ev") and shown("ev_hybrid", fuel="hybrid")
    assert not shown("ev_hybrid", fuel="petrol")


def test_clutch_by_transmission():
    for t in ("mt", "amt", "dct"):
        assert shown("clutch", fuel="petrol", transmission=t), t
    for t in ("at", "cvt"):
        assert not shown("clutch", fuel="petrol", transmission=t), t


def test_fuel_filters():
    assert [f for f in ("petrol", "diesel", "cng", "hybrid", "ev") if shown("fuel_delivery", fuel=f)] == [
        "petrol", "cng", "hybrid"]
    assert shown("cng", fuel="cng") and not shown("cng", fuel="petrol")
    assert shown("diesel", fuel="diesel") and not shown("diesel", fuel="petrol")


def test_unknown_car_sees_everything():
    assert all(shown(code) for code in CATEGORIES)
    assert shown("clutch", fuel="petrol")  # transmission unknown


def test_answered_category_kinds():
    assert CATEGORIES["number_plate"]["kind"] == "inspect"
    assert CATEGORIES["inspection"]["kind"] == "inspect"
    assert CATEGORIES["body"]["kind"] == "inspect"
    assert [s["file"] for s in CATEGORIES["suspension"]["sources"]] == [14, 17]


def test_out_of_fuel_becomes_battery_ran_out_for_pure_ev():
    topic = next(t for t in taxonomy["emergency"]["topics"] if t["code"] == "out_of_fuel")
    assert topic["label_en"] == "Petrol finished"
    [variant] = topic["variants"]
    assert variant["when"] == {"fuel": ["ev"]}
    assert variant["label_en"] == "Battery ran out" and variant["label_hi"].strip()
    assert variant["categories"] == ["ev_hybrid"]


def test_alias_map_marks_internal_columns():
    internal = {c["field"] for c in aliases["template_columns"] if c["visibility"] == "internal"}
    assert {"mechanic_task", "mechanic_repair_steps", "internal_notes"} <= internal
    ev_internal = {c["field"] for c in aliases["ev_extra_columns"] if c["visibility"] == "internal"}
    assert ev_internal == {"ev_repair_plan", "ev_repair_result_check"}
    assert len(aliases["template_columns"]) == 34
    assert len(aliases["ev_extra_columns"]) == 8
    positions = [c["position"] for c in aliases["template_columns"] + aliases["ev_extra_columns"]]
    assert positions == list(range(1, 43))


# ---------------------------------------------------------------- import_rules.yaml

rules = yaml.safe_load((SCHEMA / "import_rules.yaml").read_text(encoding="utf-8"))
FILES = {f["file_no"]: f for f in manifest["files"]}


def test_value_overrides():
    assert rules["value_overrides"]["F01-CL-02"] == {"road_repairable": "limited"}
    for key, fields in rules["value_overrides"].items():
        file_no, prefix = int(key[1:3]), key.split("-")[1]
        assert prefix in FILES[file_no]["categories"], key
        if "road_repairable" in fields:
            assert fields["road_repairable"] in ("yes", "limited", "no")


def test_cost_rules_per_file():
    costs = rules["costs"]
    assert set(costs) == {2, 6, 7}
    assert costs[2]["mode"] == "recalculate" and costs[2]["is_approx"]
    assert costs[2]["fallback_display"] == "price_on_inspection"
    assert costs[6]["mode"] == "text" and costs[6]["quotation_required"] is True
    assert costs[7]["mode"] == "range"


def test_phrase_drafting_and_accuracy_label():
    p = rules["phrases"]
    assert p["draft_for_files"] == [1, 2, 3, 4, 5, 6]
    assert p["draft_per_fault"] == {"min": 5, "max": 10}
    assert p["draft_status"] == "draft" and p["draft_is_synthetic"] is True
    assert p["accuracy_label_until_real_cases"] == "on synthetic phrases"


def test_safety_rules_are_live_before_signoff():
    assert rules["safety"] == {"import_status": "active_pending_signoff", "launch_requires_status": "approved"}


def test_file9_part_links_are_drafts():
    assert rules["part_links"][9]["status"] == "draft"


def test_image_caption_and_internal_sheets():
    assert rules["images"]["customer_caption"] == "Illustration, not an exact part drawing"
    assert {"file": 4, "sheet": "REAL IMAGE LINKS"} in rules["internal_sheets"]
