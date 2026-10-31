"""Automatic first review of the segment-parts CSVs: decisions, flags, people's decisions kept, the notes file."""

import csv

from app.parts.autoreview import REVIEWER, FileDecisions, review_segments, write_notes
from app.parts.review import EXCLUDED_FIELDS, SEGMENT_FIELDS


def row(fault_key, segment, line_no, part, price, part_type=None, kind="part", status="ok", top="", **extra):
    r = dict.fromkeys(SEGMENT_FIELDS, "")
    r.update(
        file_no="7",
        fault_key=fault_key,
        canonical_fault_key=fault_key,
        segment=segment,
        line_no=str(line_no),
        part=part,
        part_type=part_type or part,
        kind=kind,
        price_inr=str(price) if price is not None else "",
        price_max_inr=top,
        parse_status=status,
        fit_status="not model-verified",
        **extra,
    )
    return r


def write(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SEGMENT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def read(path):
    return {(r["fault_key"], r["segment"], r["line_no"]): r for r in csv.DictReader(path.open(encoding="utf-8"))}


def test_rules(tmp_path):
    peers = [row(f"F07-SS-{i:02d}", "budget", 1, "Fuel pump assembly", 5000 + i * 100) for i in range(10, 15)]
    rows = [
        row("F07-SS-01", "budget", 1, "12V car battery", 4500, status="copied_total"),
        row("F07-SS-02", "budget", 1, "Clutch plate", 2500),
        row("F07-SS-02", "premium", 1, "Clutch plate", 1800),  # premium below budget
        row("F07-SS-03", "budget", 1, "Fuel pump assembly", 450),  # a tenth of the usual price
        row("F07-SS-04", "budget", 1, "Wheel alignment (service)", 500, kind="service"),
        row("F07-SS-05", "budget", 1, "Home charger repair", 1500, top="8000"),  # very wide range
        row("F07-SS-06", "budget", 1, "Catalytic converter case", 97800),  # too dear for a budget car
        row("F07-SS-07", "budget", 1, "Quotation part", None, status="no_price"),
        row("F07-SS-08", "budget", 1, "Head gasket", 2200, approved="no", reviewed_by="Aarav"),  # a person decided
        *peers,
    ]
    write(tmp_path / "F07.csv", rows)
    (d,) = review_segments(tmp_path)
    got = read(tmp_path / "F07.csv")

    def decision(key, seg="budget"):
        r = got[(key, seg, "1")]
        return r["approved"], r["reviewer_note"]

    assert decision("F07-SS-01") == ("no", "Excluded: copied total.")
    # premium below budget: both prices are doubtful, both flagged (not loaded)
    assert decision("F07-SS-02")[0] == decision("F07-SS-02", "premium")[0] == ""
    assert "below budget" in decision("F07-SS-02", "premium")[1]
    assert decision("F07-SS-03")[0] == "" and "median" in decision("F07-SS-03")[1]
    assert decision("F07-SS-04") == ("yes", "Clear: parsed price, labour (service), not model-verified")
    assert "wide range" in decision("F07-SS-05")[1]
    assert "high for a budget car" in decision("F07-SS-06")[1]
    assert decision("F07-SS-07") == ("no", "Excluded: no price.")  # quotation only
    assert got[("F07-SS-08", "budget", "1")]["reviewed_by"] == "Aarav"  # untouched
    assert all(r["reviewed_by"] == REVIEWER for k, r in got.items() if k[0] != "F07-SS-08")
    assert (d.approved, d.rejected, len(d.flagged), d.by_human) == (6, 2, 5, 1)  # approved: 5 peers + alignment

    # re-running gives the same decisions, and the notes list the flagged prices
    review_segments(tmp_path)
    assert read(tmp_path / "F07.csv") == got
    with (tmp_path / "excluded.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=EXCLUDED_FIELDS)
        w.writeheader()
        w.writerow({"file_no": "7", "fault_key": "F07-SS-01", "parse_status": "copied_total"})
    links = FileDecisions("F09 links")
    notes = write_notes(tmp_path, [d], links).read_text(encoding="utf-8")
    assert "F07-SS-03" in notes and "Catalytic converter case" in notes and "copied total | F07 1" in notes
