"""Builds the citation object, corpus/07 section 8.

"Every number carries a citation object, and a number without a resolving
citation is not displayed." build_citation() is therefore only callable on a
CompiledMetric with status == 'ok' -- there is no number here to attach a
citation to otherwise, and CLAUDE.md invariant #7 is explicit that a blocked
metric is "not displayed. Not badged, not greyed out. Not displayed" as a
number; the UI shows the block reason instead (see src/api/routes/overview.py).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from src.semantic.compiler import CompiledMetric


class NotCitable(Exception):
    """Raised when build_citation cannot produce a citation that resolves to
    source rows. Two kinds of cause, both ending the same way -- the number is
    not displayed:

      - The metric did not resolve to a value at all. A programming error in
        the caller, not a normal outcome a user should ever see.
      - The metric resolved, but nothing backs it: no source rows, or no
        source file behind the rows. Not a caller error -- a real data
        condition, and precisely the one corpus/07 section 8 exists to catch
        ("every number is clickable through to the rows that produced it").

    Raising rather than returning a flag is deliberate. A caller that forgets
    to check a returned signal displays an uncited number; a caller that
    forgets to catch this gets an exception. Invariant #7 is not opt-in."""


@dataclass
class Citation:
    value: Decimal
    metric: str
    metric_version: int
    period: str
    basis: str
    snapshot_at: str
    reconciliation_status: str
    query_hash: str
    row_count: int
    source_facts: list[str]
    source_files: list[str]
    mapping_version: int | None
    unmapped_value_inr: Decimal | None
    drill_url: str

    def as_dict(self) -> dict:
        return {
            "value": self.value, "metric": self.metric, "metric_version": self.metric_version,
            "period": self.period, "basis": self.basis, "snapshot_at": self.snapshot_at,
            "reconciliation_status": self.reconciliation_status, "query_hash": self.query_hash,
            "row_count": self.row_count, "source_facts": self.source_facts,
            "source_files": self.source_files, "mapping_version": self.mapping_version,
            "unmapped_value_inr": self.unmapped_value_inr, "drill_url": self.drill_url,
        }


def compute_query_hash(tenant_id: str, metric_id: str, entity_id: int, period_key: str,
                          mapping_version_no: int | None, snapshot_at: str) -> str:
    """Deterministic short hash of exactly the inputs that determine the
    query -- re-running the same compile at the same snapshot_at reproduces
    the same hash, per corpus/07's 'snapshot_at means re-rendering a signed
    answer six months later reproduces it exactly.'"""
    basis = f"{tenant_id}|{metric_id}|{entity_id}|{period_key}|{mapping_version_no}|{snapshot_at}"
    return hashlib.sha256(basis.encode()).hexdigest()[:6]


def fetch_source_files(conn, schema: str, tenant_id: str, load_run_ids: set[int]) -> list[str]:
    if not load_run_ids:
        return []
    placeholders = ",".join(["%s"] * len(load_run_ids))
    with conn.cursor() as cur:
        # source_file is a shared app-schema table (db/migrations/shared/
        # 0003_source_file.sql), not per-tenant -- no schema substitution.
        cur.execute(
            f'SELECT DISTINCT file_name FROM app.source_file '
            f'WHERE tenant_id = %s AND load_run_id IN ({placeholders}) ORDER BY file_name',
            (tenant_id, *load_run_ids),
        )
        return [r[0] for r in cur.fetchall()]


def fetch_unmapped_value_inr(conn, schema: str, mapping_version_id: int) -> Decimal:
    """corpus/07 section 8's unmapped_value_inr: how much of THIS mapping
    version's universe sits in suspense.unmapped -- displayed on every
    citation, not just the data health screen, per invariant #7's spirit
    that a number is never shown without its own caveats attached."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT COALESCE(SUM(period_value_inr), 0) FROM "{schema}".map_account '
            f"WHERE mapping_version_id = %s AND canonical_class = 'suspense.unmapped'",
            (mapping_version_id,),
        )
        return cur.fetchone()[0]


def build_citation(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                     compiled: CompiledMetric, reconciliation_status: str,
                     snapshot_at: datetime | None = None) -> Citation:
    """corpus/07 section 8. A citation is only a citation if it resolves: the
    three guards below are the difference between "this number is backed by
    12,406 rows of Tally export" and "this number is backed by nothing, and
    looks identical."

    The row_count and source_files guards are not thresholds (CLAUDE.md
    section 3.2) -- zero is the structural boundary between a drill_url that
    resolves and one that does not, stated by corpus/07 section 8's own first
    property, "every number is clickable through to the rows that produced
    it." Nothing here is a materiality judgement.

    Safe across every metric shape: src/semantic/compiler.py populates
    row_count and load_run_ids from real fact rows on both the leaf path
    (_fetch_leaf_amounts' COUNT(*)) and the derived path (the summed
    dependency closure) -- so an 'ok' metric with zero rows is always a
    metric with nothing behind it, never a legitimately-empty aggregate."""
    if compiled.status != "ok" or compiled.value is None:
        raise NotCitable(f"{compiled.metric_id} did not resolve to a value (status={compiled.status})")

    if compiled.row_count == 0:
        raise NotCitable(
            f"{compiled.metric_id} resolved to {compiled.value} for {compiled.period_key}, but no source "
            f"rows produced it -- its drill_url would resolve to nothing. A value with an empty result set "
            f"behind it is not a number this system displays (corpus/07 section 8, CLAUDE.md invariant 7)."
        )

    snap = (snapshot_at or datetime.now(timezone.utc)).isoformat()
    query_hash = compute_query_hash(tenant_id, compiled.metric_id, entity_id, compiled.period_key,
                                        compiled.mapping_version_no, snap)

    source_files = fetch_source_files(conn, schema, tenant_id, compiled.load_run_ids)
    if not source_files:
        raise NotCitable(
            f"{compiled.metric_id} has {compiled.row_count} source row(s) for {compiled.period_key} but no "
            f"source file resolves behind them (load_run_ids={sorted(compiled.load_run_ids)}) -- corpus/07 "
            f"section 8's source_files is what makes the number traceable to what the client uploaded, and "
            f"an empty list traces to nothing."
        )

    unmapped = fetch_unmapped_value_inr(conn, schema, mapping_version_id)

    return Citation(
        value=compiled.value, metric=compiled.metric_id, metric_version=compiled.metric_version or 0,
        period=compiled.period_key, basis="accrual", snapshot_at=snap,
        reconciliation_status=reconciliation_status, query_hash=query_hash, row_count=compiled.row_count,
        source_facts=compiled.source_facts, source_files=source_files,
        mapping_version=compiled.mapping_version_no, unmapped_value_inr=unmapped,
        drill_url=f"/query/{query_hash}/rows",
    )
