"""Tests for backdated-entry detection, corpus/04 section 5."""
from datetime import date

from src.ingest.repull import find_backdated_entries


def test_detects_entry_date_after_event_date_within_window():
    rows = [
        {"source_record_id": "V1#1", "voucher_no": "V1", "event_date": "2026-01-10", "entry_date": "2026-02-15"},
    ]
    found = find_backdated_entries(rows, as_of=date(2026, 3, 1))
    assert len(found) == 1
    assert found[0].days_late == 36


def test_ignores_entries_not_backdated():
    rows = [{"source_record_id": "V1#1", "voucher_no": "V1", "event_date": "2026-02-15", "entry_date": "2026-02-15"}]
    assert find_backdated_entries(rows, as_of=date(2026, 3, 1)) == []


def test_ignores_backdated_entries_outside_the_trailing_window():
    # entry_date is far outside the 90-day trailing window from as_of.
    rows = [{"source_record_id": "V1#1", "voucher_no": "V1", "event_date": "2020-01-01", "entry_date": "2020-06-01"}]
    assert find_backdated_entries(rows, as_of=date(2026, 3, 1), window_days=90) == []


def test_synthetic_manufacturer_defect_1_is_detected():
    """The seeded backdated batch from corpus/11 section 2.2 defect #1:
    event_date in an early, already-'locked' month, entry_date ~23 months
    later. as_of set to the entry month makes it fall inside a 90-day
    trailing window from itself."""
    from synthetic.manufacturer.engine import build_company
    data = build_company(seed=42)
    entry = next(e for e in data.defect_log.entries if e["defect_id"] == 1)
    event_month = entry["event_month"]
    entry_month = entry["entry_month"]
    assert event_month != entry_month

    all_rows = [r for month_rows in data.gl_rows.values() for r in month_rows]
    backdated_rows = [
        {"source_record_id": f'{r["voucher_no"]}#{r["line_no"]}', "voucher_no": r["voucher_no"],
          "event_date": r["voucher_date"], "entry_date": r["entry_date"]}
        for r in all_rows
    ]
    as_of = date.fromisoformat(entry_month + "-28")
    found = find_backdated_entries(backdated_rows, as_of=as_of, window_days=90)
    assert any(f.voucher_no == entry["voucher_no"] for f in found)
