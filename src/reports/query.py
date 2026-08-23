"""Resolves the effective mapping version for a period and reads
fact_gl_entry grouped by canonical class through it.

Implements corpus/06 section 6 rule 3: "Effective dating is by accounting
period. A version effective from 1 April 2026 applies to April onwards;
March renders with the prior version forever." Statement assembly never
trusts fact_gl_entry.mapping_version_id for classification (that column
records which version was the ingestion-time placeholder, not necessarily
which version governs this period, per the sprint 1/2 handoff) -- it always
resolves the version whose effective_from/effective_to covers the period
being reported, and joins through map_account for that version specifically.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal


class NoApprovedMappingError(Exception):
    """corpus/06 section 6 rule 1: 'Metrics do not unlock until version 1 is
    approved... no statement and no metric.'"""


def resolve_mapping_version_for_period(conn, schema: str, tenant_id: str, entity_id: int,
                                          period_end: date) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT mapping_version_id FROM "{schema}".mapping_version '
            f"WHERE tenant_id = %s AND entity_id = %s AND status = 'approved' "
            f'AND effective_from <= %s AND effective_to > %s',
            (tenant_id, entity_id, period_end, period_end),
        )
        row = cur.fetchone()
    if not row:
        raise NoApprovedMappingError(
            f"no approved mapping version covers {period_end} for entity {entity_id} -- "
            f"corpus/06 section 6 rule 1: no statement generates before version 1 is approved"
        )
    return row[0]


def class_movements(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                      date_from: date, date_to: date) -> dict[str, Decimal]:
    """Period flow: sum(amount_base) grouped by canonical_class, for facts
    with event_date in [date_from, date_to]. Dr positive, Cr negative, per
    corpus/03 section 1 -- the caller applies the statement's sign, not this
    query."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT ma.canonical_class, SUM(fg.amount_base) '
            f'FROM "{schema}".fact_gl_entry fg '
            f'JOIN "{schema}".dim_account da ON da.account_key = fg.account_key '
            f'JOIN "{schema}".map_account ma ON ma.mapping_version_id = %s AND ma.source_record_id = da.source_record_id '
            f'WHERE fg.tenant_id = %s AND fg.entity_id = %s AND fg.is_current '
            f'AND fg.event_date BETWEEN %s AND %s '
            f'GROUP BY ma.canonical_class',
            (mapping_version_id, tenant_id, entity_id, date_from, date_to),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def class_balances(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                     as_of_date: date) -> dict[str, Decimal]:
    """Cumulative balance as of a date: sum(amount_base) for event_date <=
    as_of_date, grouped by canonical_class. For balance sheet assembly."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT ma.canonical_class, SUM(fg.amount_base) '
            f'FROM "{schema}".fact_gl_entry fg '
            f'JOIN "{schema}".dim_account da ON da.account_key = fg.account_key '
            f'JOIN "{schema}".map_account ma ON ma.mapping_version_id = %s AND ma.source_record_id = da.source_record_id '
            f'WHERE fg.tenant_id = %s AND fg.entity_id = %s AND fg.is_current '
            f'AND fg.event_date <= %s '
            f'GROUP BY ma.canonical_class',
            (mapping_version_id, tenant_id, entity_id, as_of_date),
        )
        return {row[0]: row[1] for row in cur.fetchall()}
