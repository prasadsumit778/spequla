"""Tests for the Indian fiscal calendar, corpus/04 section 3.1."""
from datetime import date

from src.ingest.calendar import dim_date_row, fiscal_quarter, fiscal_year, generate_dim_date_rows


def test_fiscal_year_april_start():
    assert fiscal_year(date(2026, 4, 1)) == 2027   # FY2027 starts April 2026
    assert fiscal_year(date(2026, 3, 31)) == 2026   # still FY2026


def test_fiscal_quarter():
    assert fiscal_quarter(date(2026, 4, 15)) == 1
    assert fiscal_quarter(date(2026, 6, 30)) == 1
    assert fiscal_quarter(date(2026, 7, 1)) == 2
    assert fiscal_quarter(date(2027, 3, 31)) == 4


def test_fiscal_month_num_april_is_1():
    row = dim_date_row(date(2026, 4, 1))
    assert row["fiscal_month_num"] == 1
    row = dim_date_row(date(2027, 3, 1))
    assert row["fiscal_month_num"] == 12


def test_period_key_format():
    row = dim_date_row(date(2026, 4, 5))
    assert row["period_key"] == "2026-04"


def test_month_end_flags():
    row = dim_date_row(date(2026, 4, 30))
    assert row["is_month_end"] is True
    row = dim_date_row(date(2026, 4, 29))
    assert row["is_month_end"] is False


def test_quarter_end_and_fy_end():
    q_end = dim_date_row(date(2026, 6, 30))
    assert q_end["is_quarter_end"] is True
    fy_end = dim_date_row(date(2027, 3, 31))
    assert fy_end["is_fiscal_year_end"] is True
    assert fy_end["is_quarter_end"] is True


def test_generate_range_covers_every_day():
    rows = generate_dim_date_rows(date(2026, 4, 1), date(2026, 4, 30))
    assert len(rows) == 30
    assert rows[0]["date_key"] == "2026-04-01"
    assert rows[-1]["date_key"] == "2026-04-30"
