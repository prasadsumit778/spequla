"""The Indian fiscal calendar. Implements corpus/04 section 3.1 verbatim.

dim_date "owns the fiscal calendar... nowhere else. Every 'last quarter'
resolution, every year-on-year comparison and every period lock reads from
this table. A fiscal year computed inline in application code is a defect" --
so this module exists once, and every other module that needs a fiscal year,
quarter or period key computes it by generating (or looking up) a dim_date
row, never by re-deriving the arithmetic elsewhere.

FY start month is April, per D-038 (resolved).
"""
from __future__ import annotations

import calendar as _calendar
from datetime import date, timedelta

FISCAL_START_MONTH = 4  # April, D-038


def fiscal_year(d: date) -> int:
    """FY2027 = Apr 2026 to Mar 2027."""
    return d.year + 1 if d.month >= FISCAL_START_MONTH else d.year


def fiscal_quarter(d: date) -> int:
    """Q1 = Apr, May, Jun."""
    fiscal_month = fiscal_month_num(d)
    return (fiscal_month - 1) // 3 + 1


def fiscal_month_num(d: date) -> int:
    """April = 1."""
    return (d.month - FISCAL_START_MONTH) % 12 + 1


def period_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_end(d: date) -> date:
    last_day = _calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last_day)


def is_quarter_end_month(d: date) -> bool:
    return fiscal_month_num(d) in (3, 6, 9, 12)


def is_fiscal_year_end_month(d: date) -> bool:
    return fiscal_month_num(d) == 12  # March


def dim_date_row(d: date) -> dict:
    fy = fiscal_year(d)
    me = month_end(d)
    return {
        "date_key": d.isoformat(),
        "day_of_month": d.day,
        "month_num": d.month,
        "month_name": d.strftime("%B"),
        "calendar_year": d.year,
        "calendar_quarter": (d.month - 1) // 3 + 1,
        "fiscal_year": fy,
        "fiscal_year_label": f"FY{fy - 2000:02d}",
        "fiscal_quarter": fiscal_quarter(d),
        "fiscal_month_num": fiscal_month_num(d),
        "period_key": period_key(d),
        "is_month_end": d == me,
        "is_quarter_end": d == me and is_quarter_end_month(d),
        "is_fiscal_year_end": d == me and is_fiscal_year_end_month(d),
        "days_in_month": me.day,
    }


def generate_dim_date_rows(start: date, end: date) -> list[dict]:
    """One row per calendar day, start to end inclusive."""
    rows = []
    d = start
    one_day = timedelta(days=1)
    while d <= end:
        rows.append(dim_date_row(d))
        d += one_day
    return rows
