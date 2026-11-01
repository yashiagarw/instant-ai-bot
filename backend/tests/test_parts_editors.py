"""Phase 4.4 part 2: the vehicle catalogue editor (live, audited, kept by the seed), Parts & Prices edits in a draft
(survive parts build, source and date required, the second look on prices of 20,000 rupees or more by another
person), zone labour rates used by estimates after publish, the CSV import, uploaded pictures through the photo
storage, bulk sign-off with one audit entry, and who may do it."""

import io
from datetime import date

import pytest
from PIL import Image as PILImage
from sqlalchemy import func, select

from app.admin.models import AuditLog
from app.estimates.zones import version_zone_rates
from app.knowledge.models import DatasetVersion, Image
from app.parts.models import Part, PartCompatibility, PartPrice
from app.uploads.storage import MemoryStorage
from app.vehicles.models import Make, Model, Variant
from app.vehicles.seed import CatalogueFile, seed
from tests.test_admin import app, browser, code, make_staff  # noqa: F401
from tests.test_datasets import live, set_eval, staff, world  # noqa: F401
from tests.test_knowledge_editors import publish, save, start_draft

TODAY = date.today().isoformat()


@pytest.fixture
def boss(staff):  # noqa: F811
    return staff["super_admin"]


@pytest.fixture
def editor(staff):  # noqa: F811
    return staff["content_admin"]


def actions(db_session) -> list[str]:
    return list(db_session.scalars(select(AuditLog.action).order_by(AuditLog.id)))


def a_car(client) -> dict:
    make = client.post("/api/admin/vehicles/makes", json={"name": "Maruti Suzuki", "aliases": "maruti"}).json()
    model = client.post("/api/admin/vehicles/models", json={"make_id": make["id"], "name": "Swift"}).json()
    return {"make": make, "model": model}


# ---------------------------------------------------------------- vehicles


def test_catalogue_editor_is_live_audited_and_kept_by_the_seed(db_session, world, editor):  # noqa: F811
    car = a_car(editor)
    gen = editor.post(
        "/api/admin/vehicles/generations",
        json={"model_id": car["model"]["id"], "name": "3rd gen", "year_from": 2018, "year_to": 2023},
    ).json()
    body = {
        "model_id": car["model"]["id"],
        "generation_id": gen["id"],
        "fuel": "petrol",
        "transmission": "amt",
        "year_from": 2018,
        "year_to": 2023,
        "price_segment": "budget",
        "features": {"start_stop": False},
    }
    v = editor.post("/api/admin/vehicles/variants", json=body)
    assert v.status_code == 201, v.text
    assert v.json()["name"] == "2018-2023 Petrol AMT" and v.json()["edited_by"] == "content@im.test"
    r = editor.put(f"/api/admin/vehicles/variants/{v.json()['id']}", json={**body, "price_segment": "mid"})
    assert r.status_code == 200 and r.json()["price_segment"] == "mid"
    assert editor.post("/api/admin/vehicles/variants", json=body).status_code == 409  # the same variant twice
    bad = editor.post("/api/admin/vehicles/variants", json={**body, "features": {"warp_drive": True}})
    assert bad.status_code == 422
    tree = editor.get("/api/admin/vehicles/catalogue").json()
    swift = tree["makes"][0]["models"][0]
    assert swift["generations"][0]["name"] == "3rd gen" and swift["variants"][0]["generation_id"] == gen["id"]
    assert {"vehicle.make_create", "vehicle.variant_update"} <= set(actions(db_session))

    # The seed keeps the admin's change (mid) instead of the file's (budget) and never prunes admin rows.
    catalogue = CatalogueFile.model_validate(
        {
            "version": 1,
            "makes": [
                {
                    "name": "Maruti Suzuki",
                    "models": [
                        {
                            "name": "Swift",
                            "variants": [
                                {"years": [2018, 2023], "fuel": "petrol", "transmissions": ["amt"], "segment": "budget"}
                            ],
                        }
                    ],
                }
            ],
        }
    )
    report = seed(db_session, catalogue, prune=True)
    variant = db_session.get(Variant, v.json()["id"])
    db_session.refresh(variant)
    assert variant.price_segment == "mid" and "Variant Swift 2018-2023 Petrol AMT" in report.kept_admin_edits
    assert report.deleted == 0


def test_a_variant_in_use_cannot_be_deleted(db_session, world, editor):  # noqa: F811
    from app.diagnosis.models import DiagnosisSession

    car = a_car(editor)
    v = editor.post(
        "/api/admin/vehicles/variants",
        json={
            "model_id": car["model"]["id"],
            "fuel": "petrol",
            "transmission": "mt",
            "year_from": 2020,
            "price_segment": "budget",
        },
    ).json()
    db_session.add(
        DiagnosisSession(variant_id=v["id"], vehicle_snapshot={}, anon_key_hash="x" * 64, engine_version="2.3.0")
    )
    db_session.commit()
    r = editor.delete(f"/api/admin/vehicles/variants/{v['id']}")
    assert r.status_code == 409 and "diagnoses or saved cars" in r.json()["detail"]
    assert editor.delete(f"/api/admin/vehicles/models/{car['model']['id']}").status_code == 409


# ---------------------------------------------------------------- parts & prices


PART = {"description": "Front brake pads", "part_type": "Brake pad set", "brand": "Bosch", "part_number": "0986AB1234"}


def price(amount, **kw):
    return {"price_inr": amount, "supplier": "Boodmo", "checked_on": TODAY, **kw}


def test_parts_prices_and_fits_go_into_the_draft_and_survive_a_rebuild(db_session, world, editor):  # noqa: F811
    car = a_car(editor)
    v = start_draft(editor)
    r = save(editor, v, "part", "", PART)
    assert r.status_code == 200, r.text
    key = r.json()["key"]
    assert key == "PN:bosch:0986AB1234:1"
    # A price needs a source and a date.
    assert save(editor, v, "part_price", f"{key}|budget|", {"price_inr": 1450, "checked_on": TODAY}).status_code == 422
    assert save(editor, v, "part_price", f"{key}|budget|", {"price_inr": 1450, "supplier": "Boodmo"}).status_code == 422
    r = save(editor, v, "part_price", f"{key}|budget|", price(1450, price_max_inr=1700))
    assert r.status_code == 200 and r.json()["key"] == f"{key}|budget|editor-1" and r.json()["warning"] is None
    fit = {"model_id": car["model"]["id"], "year_from": 2018, "year_to": 2023, "fit_text": "Swift 2018-23"}
    r = save(editor, v, "part_fit", f"{key}|", fit)
    assert r.status_code == 200, r.text

    detail = editor.get(f"/api/admin/parts/versions/{v}/parts/{key}").json()
    assert [(p["price_inr"], p["supplier"]) for p in detail["prices"]] == [(1450, "Boodmo")]
    assert detail["fits"][0]["model"] == "Maruti Suzuki Swift"
    assert db_session.scalar(select(func.count()).where(PartPrice.dataset_version_id == world["first"].id)) == 0

    # Rebuilding the draft runs parts build again: the edits are applied after it.
    assert editor.post(f"/api/admin/datasets/versions/{v}/rebuild").status_code == 202
    detail = editor.get(f"/api/admin/parts/versions/{v}/parts/{key}").json()
    assert len(detail["prices"]) == 1 and len(detail["fits"]) == 1
    steps = db_session.get(DatasetVersion, v).validation["steps"]["steps"]
    assert steps["parts edits apply"].startswith("3 edits applied")

    # A change to an existing part is live only after publish.
    save(editor, v, "part", key, {**PART, "description": "Front brake pads (ceramic)"})
    assert db_session.scalar(select(Part.description).where(Part.part_key == key)) == "Front brake pads"
    publish(editor, db_session, v)
    db_session.expire_all()
    assert db_session.scalar(select(Part.description).where(Part.part_key == key)) == "Front brake pads (ceramic)"
    assert db_session.scalar(select(func.count()).where(PartCompatibility.dataset_version_id == v)) == 1


def test_a_big_price_needs_a_second_look_by_someone_else(db_session, world, editor, boss):  # noqa: F811
    v = start_draft(editor)
    key = save(editor, v, "part", "", {**PART, "part_number": "", "description": "Clutch kit"}).json()["key"]
    r = save(editor, v, "part_price", f"{key}|premium|", price(24000))
    assert "20,000 rupees or more" in r.json()["warning"]
    pkey = r.json()["key"]
    summary = editor.get(f"/api/admin/datasets/versions/{v}").json()["editor"]["second_look"]
    assert summary["count"] == 1 and summary["items"][0]["key"] == pkey

    mine = editor.post(f"/api/admin/parts/versions/{v}/prices/second-look", json={"key": pkey})
    assert mine.status_code == 422 and "you entered it" in mine.json()["detail"]
    other = boss.post(f"/api/admin/parts/versions/{v}/prices/second-look", json={"key": pkey})
    assert other.status_code == 200 and other.json()["second_look_by"] == "boss@im.test"
    assert editor.get(f"/api/admin/datasets/versions/{v}").json()["editor"]["second_look"]["count"] == 0
    # Changing the price again needs a new second look.
    save(boss, v, "part_price", pkey, {**price(26000), "second_look_by": None})
    assert editor.get(f"/api/admin/datasets/versions/{v}").json()["editor"]["second_look"]["count"] == 1


def test_zone_labour_rates_are_used_by_estimates_after_publish(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    rate = {
        "rate_min_inr": 500,
        "rate_max_inr": 700,
        "source": "5 garages, Sector 14-56, phone survey",
        "checked_on": TODAY,
    }
    assert save(editor, v, "zone_rate", "gurugram|budget", {**rate, "source": ""}).status_code == 422
    assert save(editor, v, "zone_rate", "atlantis|budget", rate).status_code == 422
    assert save(editor, v, "zone_rate", "gurugram|budget", rate).status_code == 200
    grid = editor.get(f"/api/admin/parts/versions/{v}/labour").json()["zones"]
    assert next(z for z in grid if z["key"] == "gurugram|budget")["rate_min_inr"] == 500
    assert version_zone_rates(db_session, live(db_session)) == {}  # not live yet
    export = editor.get(f"/api/admin/parts/versions/{v}/zone-rates.yaml").text
    assert "gurugram:" in export and "- 500" in export and "phone survey" in export
    publish(editor, db_session, v)
    rates = version_zone_rates(db_session, live(db_session))
    assert rates[("gurugram", "budget")].rate.low == 500 and rates[("gurugram", "budget")].source.startswith(
        "5 garages"
    )


def test_csv_import_preview_then_into_the_draft(db_session, world, editor):  # noqa: F811
    a_car(editor)
    v = start_draft(editor)
    header = "part_type,description,brand,part_number,quantity,segment,price_inr,price_max_inr,supplier,source_url,checked_on,make,model,year_from,year_to,fuel,transmission,note\n"  # noqa: E501
    rows = [
        f"Brake pad set,Front pads,Bosch,PAD1,1,budget,1450,,Boodmo,,{TODAY},Maruti Suzuki,Swift,2018,2023,petrol,,\n",
        f"Gearbox,Gearbox assembly,Maruti Genuine,GB1,1,mid,52000,,Dealer quote,,{TODAY},,,,,,,\n",
        f"Wiper,Wiper blade,,,1,cheap,300,,,,{TODAY},,,,,,,\n",
        "Bulb,Headlamp bulb,Philips,H4,1,budget,450,,Amazon,,,Tata,Nano,,,,,\n",
    ]
    body = (header + "".join(rows)).encode()
    preview = editor.post(f"/api/admin/parts/versions/{v}/import", content=body).json()
    assert preview["summary"] == {"rows": 4, "valid": 2, "errors": 2, "flagged": 1}
    errors = {r["line"]: r["errors"] for r in preview["rows"]}
    assert any("segment" in e for e in errors[4]) and any("source" in e for e in errors[4])
    assert any("checked_on" in e for e in errors[5]) and any("unknown car Tata Nano" in e for e in errors[5])
    assert db_session.scalar(select(func.count()).select_from(PartPrice).where(PartPrice.dataset_version_id == v)) == 0

    done = editor.post(f"/api/admin/parts/versions/{v}/import?commit=true", content=body)
    assert done.status_code == 200, done.text
    prices = db_session.scalars(select(PartPrice).where(PartPrice.dataset_version_id == v)).all()
    assert sorted(p.price_inr for p in prices) == [1450, 52000]
    assert (
        db_session.scalar(
            select(func.count()).select_from(PartCompatibility).where(PartCompatibility.dataset_version_id == v)
        )
        == 1
    )
    assert actions(db_session).count("parts.csv_import") == 1
    assert "knowledge.edit" not in actions(db_session)  # one audit entry for the whole import


# ---------------------------------------------------------------- pictures


def png_bytes() -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (40, 30), "orange").save(buf, format="PNG")
    return buf.getvalue()


def test_uploaded_pictures_go_through_the_photo_storage_and_link_to_faults(db_session, world, editor, app):  # noqa: F811
    app.state.storage = storage = MemoryStorage()
    r = editor.post("/api/admin/media/pictures", params={"caption": "Swollen battery"}, content=png_bytes())
    assert r.status_code == 201, r.text
    sha = r.json()["sha1"]
    assert r.json()["url"] == f"/media/uploaded/{sha}.jpg"
    assert list(storage.objects) == [f"media/uploaded/{sha}.jpg"]  # incoming copy removed; clean JPEG kept
    assert storage.objects[f"media/uploaded/{sha}.jpg"][1] == "image/jpeg"
    assert db_session.scalar(select(Image.caption).where(Image.sha1 == sha)) == "Swollen battery"
    bad = editor.post("/api/admin/media/pictures", content=b"GIF89a not a picture")
    assert bad.status_code == 422

    served = browser(app).get(f"/media/uploaded/{sha}.jpg", follow_redirects=False)
    assert served.status_code == 307 and served.headers["location"].startswith("https://storage.test/media/uploaded/")
    assert browser(app).get(f"/media/uploaded/{'0' * 40}.jpg", follow_redirects=False).status_code == 404

    v = start_draft(editor)
    assert save(editor, v, "fault_images", "F08-BT-03", {"images": [sha]}).status_code == 200
    detail = editor.get(f"/api/admin/knowledge/versions/{v}/faults/F08-BT-03").json()
    assert detail["images"] == [{"sha1": sha, "url": f"/media/uploaded/{sha}.jpg", "caption": "Swollen battery"}]


# ---------------------------------------------------------------- bulk sign-off and permissions


def test_bulk_sign_off_is_one_audit_entry_with_the_count_and_filter(db_session, world, editor):  # noqa: F811
    v = start_draft(editor)
    queue = editor.get(f"/api/admin/knowledge/versions/{v}/signoff").json()
    pending = [{"entity": x["entity"], "key": x["key"]} for x in queue if x["pending"]]
    assert len(pending) >= 2
    before = len(actions(db_session))
    flt = {"pending_only": True, "type": "all", "search": ""}
    r = editor.post(f"/api/admin/knowledge/versions/{v}/signoff/bulk", json={"items": pending, "filter": flt})
    assert r.status_code == 200 and r.json()["signed_off"] == len(pending)
    new = db_session.scalars(select(AuditLog).order_by(AuditLog.id).offset(before)).all()
    assert [a.action for a in new] == ["knowledge.signoff_bulk"]
    assert new[0].before == {"filter": flt} and new[0].after["signed_off"] == len(pending)
    assert not any(x["pending"] for x in editor.get(f"/api/admin/knowledge/versions/{v}/signoff").json())


def test_support_agents_cannot_edit_vehicles_parts_or_pictures(app, db_session, test_settings, world, staff):  # noqa: F811
    v = start_draft(staff["content_admin"])
    _, secret = make_staff(db_session, test_settings, "agent2@im.test", ["support_agent"])
    agent = browser(app)
    agent.post(
        "/api/admin/auth/login",
        json={"email": "agent2@im.test", "password": "correct horse battery staple", "code": code(secret)},
    )
    calls = [
        ("GET", "/api/admin/vehicles/catalogue", None),
        ("POST", "/api/admin/vehicles/makes", {"name": "Tata"}),
        ("PUT", "/api/admin/vehicles/variants/1", {}),
        ("DELETE", "/api/admin/vehicles/models/1", None),
        ("GET", f"/api/admin/parts/versions/{v}/parts", None),
        ("GET", f"/api/admin/parts/versions/{v}/prices", None),
        ("POST", f"/api/admin/parts/versions/{v}/prices/second-look", {"key": "x"}),
        ("POST", f"/api/admin/parts/versions/{v}/import", None),
        ("POST", "/api/admin/media/pictures", None),
        ("POST", f"/api/admin/knowledge/versions/{v}/signoff/bulk", {"items": [], "filter": {}}),
    ]
    for method, path, body in calls:
        assert agent.request(method, path, json=body).status_code == 403, path
    assert db_session.scalar(select(func.count()).select_from(Make)) == 0
    assert db_session.scalar(select(func.count()).select_from(Model)) == 0
