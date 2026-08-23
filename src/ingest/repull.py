"""Trailing re-pull and backdated-entry detection.

Implements corpus/04 section 5 ("Backdated entries are the normal case, not
the exception. Every run re-pulls a trailing window, defaulting to ninety
days... Anything found in that window with entry_date > event_date is a
backdated entry") and powers the bitemporal query pair from corpus/04 section
1.1: "as reported on 8 July" (valid_from <= X < valid_to) vs "as it stands
now" (is_current = true).

Sprint 1 proves the detection half only -- per the sprint 0 plan's note that
the full period_lock / restatement state machine is sprint 3 scope. What's
here: find backdated rows, and answer both bitemporal questions for a period.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

TRAILING_WINDOW_DAYS = 90


@dataclass
class BackdatedEntry:
    source_record_id: str
    voucher_no: str
    event_date: date
    entry_date: date
    days_late: int


def find_backdated_entries(rows: list[dict], as_of: date,
                             window_days: int = TRAILING_WINDOW_DAYS) -> list[BackdatedEntry]:
    """Pure function over staged/canonical rows carrying event_date and
    entry_date -- no DB dependency, so this is unit testable directly. Mirrors
    the ix_gl_backdated partial index: entry_date > event_date, and the entry
    itself falls inside the trailing window from as_of."""
    window_start = as_of - timedelta(days=window_days)
    out = []
    for r in rows:
        event_date = r["event_date"] if isinstance(r["event_date"], date) else date.fromisoformat(r["event_date"])
        entry_date = r["entry_date"] if isinstance(r["entry_date"], date) else date.fromisoformat(r["entry_date"])
        if entry_date > event_date and window_start <= entry_date <= as_of:
            out.append(BackdatedEntry(
                source_record_id=r.get("source_record_id", ""), voucher_no=r.get("voucher_no", ""),
                event_date=event_date, entry_date=entry_date, days_late=(entry_date - event_date).days,
            ))
    return out


def query_backdated_entries(conn, schema: str, tenant_id: str, as_of: date,
                              window_days: int = TRAILING_WINDOW_DAYS) -> list[BackdatedEntry]:
    """DB-backed equivalent, reading current fact_gl_entry rows."""
    window_start = as_of - timedelta(days=window_days)
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_record_id, voucher_no, event_date, entry_date FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id=%s AND is_current AND entry_date > event_date '
            f'AND entry_date BETWEEN %s AND %s',
            (tenant_id, window_start, as_of),
        )
        return [
            BackdatedEntry(source_record_id=r[0], voucher_no=r[1], event_date=r[2], entry_date=r[3],
                             days_late=(r[3] - r[2]).days)
            for r in cur.fetchall()
        ]


def sum_amount_base_as_reported_on(conn, schema: str, tenant_id: str, period_key: str,
                                     as_of: datetime) -> Decimal:
    """'As reported on 8 July': the knowledge-time snapshot query, corpus/04
    section 1.1. valid_from <= as_of < valid_to, regardless of is_current --
    a row later closed and superseded still counts if it was current at the
    snapshot instant."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(amount_base), 0) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id=%s AND period_key=%s AND valid_from <= %s AND valid_to > %s',
            (tenant_id, period_key, as_of, as_of),
        )
        return cur.fetchone()[0]


def sum_amount_base_as_it_stands_now(conn, schema: str, tenant_id: str, period_key: str) -> Decimal:
    """'As it stands now': is_current = true, corpus/04 section 1.1."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(amount_base), 0) FROM "{schema}".fact_gl_entry '
            f'WHERE tenant_id=%s AND period_key=%s AND is_current',
            (tenant_id, period_key),
        )
        return cur.fetchone()[0]
