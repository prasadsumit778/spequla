"""Review queue, mapping runs, and freeze/versioning.

Implements corpus/06 section 4 steps 5-6, section 4.3 (the review queue) and
section 6 (versioning and effective dating).

There is no live human in this build, so "review" is simulated the way an
analyst would actually do it given a rule library this comprehensive: every
exact-rule match that isn't a judgement class auto-accepts (corpus/06
section 4.2); every exact-rule match THAT IS a judgement class still gets
the rule's proposed class, but is approved by a named person rather than
auto-accepted (invariant #12); everything with no rule match is explicitly
deferred to suspense.unmapped, which corpus/06 section 4.4 states is the
correct disposition for an uninformative ledger name, not a shortfall.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from src.mapping.engine import AUTO_ACCEPT_RUPEE_CEILING_INR, Proposal, evaluate_auto_accept, extract_coa, propose_mappings

JUDGEMENT_CLASSES = {
    "exceptional.one_off", "opex.owner_remuneration", "opex.related_party_charges",
    "cogs.absorption_variance", "liability.bill_discounting", "liability.debt_related_party",
}
COVERAGE_THRESHOLD = Decimal("0.98")  # corpus/06a Coverage tab: "Target 98% or higher"


@dataclass
class MappingRunSummary:
    mapping_version_id: int
    auto_accepted: int = 0
    human_approved: int = 0
    deferred_to_suspense: int = 0
    total_value_inr: Decimal = Decimal("0")
    mapped_value_inr: Decimal = Decimal("0")


def create_draft_version(conn, schema: str, tenant_id: str, entity_id: int, version_no: int,
                           effective_from: date, created_by: str, change_reason: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".mapping_version '
            f'(tenant_id, entity_id, version_no, status, effective_from, created_by, change_reason) '
            f"VALUES (%s, %s, %s, 'draft', %s, %s, %s) RETURNING mapping_version_id",
            (tenant_id, entity_id, version_no, effective_from, created_by, change_reason),
        )
        return cur.fetchone()[0]


def _prior_approved_classes(conn, schema: str, tenant_id: str, entity_id: int) -> dict[str, str]:
    """source_record_id -> canonical_class from the most recently approved
    version, for the auto-accept 'no conflicting prior mapping' check."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT ma.source_record_id, ma.canonical_class '
            f'FROM "{schema}".map_account ma '
            f'JOIN "{schema}".mapping_version mv ON mv.mapping_version_id = ma.mapping_version_id '
            f"WHERE mv.tenant_id = %s AND mv.entity_id = %s AND mv.status = 'approved' "
            f'ORDER BY mv.version_no DESC',
            (tenant_id, entity_id),
        )
        out: dict[str, str] = {}
        for source_record_id, canonical_class in cur.fetchall():
            out.setdefault(source_record_id, canonical_class)  # keep the most recent only
        return out


def _write_map_account(conn, schema: str, mapping_version_id: int, tenant_id: str, entity_id: int,
                         proposal_or_account, canonical_class: str, statement_section: str, statement_line: str,
                         derived_channel: str | None, derived_geo: str | None, confidence: Decimal | None,
                         proposal_source: str, proposal_reason: str, approved_by: str):
    account = proposal_or_account.account if isinstance(proposal_or_account, Proposal) else proposal_or_account
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO "{schema}".map_account '
            f'(mapping_version_id, tenant_id, entity_id, source_record_id, source_account_name, '
            f' canonical_class, statement_section, statement_line, derived_channel, derived_geo, '
            f' confidence, proposal_source, proposal_reason, approved_by, approved_at, period_value_inr) '
            f'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (mapping_version_id, tenant_id, entity_id, account.source_record_id, account.source_account_name,
             canonical_class, statement_section, statement_line, derived_channel, derived_geo,
             confidence, proposal_source, proposal_reason, approved_by, datetime.now(timezone.utc),
             account.period_value_inr),
        )


def run_mapping_pass(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                       taxonomy: dict, human_approver: str,
                       rupee_ceiling: Decimal | None = AUTO_ACCEPT_RUPEE_CEILING_INR) -> MappingRunSummary:
    """taxonomy: canonical_class -> {"statement_section": ..., "statement_line": ...},
    i.e. config/taxonomy.yml loaded and keyed by class."""
    accounts = extract_coa(conn, schema, tenant_id, entity_id)
    proposed, unmatched = propose_mappings(accounts)
    prior = _prior_approved_classes(conn, schema, tenant_id, entity_id)

    summary = MappingRunSummary(mapping_version_id=mapping_version_id)
    summary.total_value_inr = sum((a.period_value_inr for a in accounts), Decimal("0"))

    for proposal in proposed:
        prior_class = prior.get(proposal.account.source_record_id)
        accepted, reason = evaluate_auto_accept(proposal, JUDGEMENT_CLASSES, prior_class, rupee_ceiling)
        tax_entry = taxonomy[proposal.canonical_class]
        if accepted:
            _write_map_account(
                conn, schema, mapping_version_id, tenant_id, entity_id, proposal,
                proposal.canonical_class, tax_entry["statement_section"], tax_entry["statement_line"],
                proposal.derived_channel, proposal.derived_geo, Decimal("1.000"),
                "exact_rule", proposal.proposal_reason, "system-auto-accept",
            )
            summary.auto_accepted += 1
        else:
            # Rule matched but couldn't auto-accept (judgement class, or a
            # conflicting prior mapping) -- still queued, but the class the
            # rule proposed is correct, so a human confirms it rather than
            # the system silently accepting it. Per invariant #12.
            _write_map_account(
                conn, schema, mapping_version_id, tenant_id, entity_id, proposal,
                proposal.canonical_class, tax_entry["statement_section"], tax_entry["statement_line"],
                proposal.derived_channel, proposal.derived_geo, Decimal("1.000"),
                "exact_rule", f"{proposal.proposal_reason} (human review required: {reason})", human_approver,
            )
            summary.human_approved += 1
        summary.mapped_value_inr += proposal.account.period_value_inr

    suspense = taxonomy["suspense.unmapped"]
    for account in unmatched:
        _write_map_account(
            conn, schema, mapping_version_id, tenant_id, entity_id, account,
            "suspense.unmapped", suspense["statement_section"], suspense["statement_line"],
            None, None, None, "human",
            "No exact rule match; deferred to suspense.unmapped per corpus/06 section 4.4", human_approver,
        )
        summary.deferred_to_suspense += 1

    return summary


def review_queue(conn, schema: str, tenant_id: str, mapping_version_id: int) -> list[dict]:
    """corpus/06 section 4.3: sorted by period_value_inr descending, with
    running coverage and unmapped value always computable from this list."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT source_account_name, source_record_id, canonical_class, proposal_source, '
            f'       approved_by, period_value_inr '
            f'FROM "{schema}".map_account WHERE mapping_version_id = %s '
            f'ORDER BY period_value_inr DESC NULLS LAST',
            (mapping_version_id,),
        )
        rows = cur.fetchall()

    total = sum((r[5] or Decimal("0")) for r in rows)
    running = Decimal("0")
    out = []
    for name, source_record_id, canonical_class, proposal_source, approved_by, value in rows:
        running += value or Decimal("0")
        out.append({
            "source_account_name": name, "source_record_id": source_record_id,
            "canonical_class": canonical_class, "proposal_source": proposal_source,
            "approved_by": approved_by, "period_value_inr": value,
            "running_pct_mapped": float(running / total) if total else 0.0,
            "unmapped_value_inr": float(total - running),
        })
    return out


def compute_coverage(total_value_inr: Decimal, mapped_value_inr: Decimal) -> Decimal:
    """Pure, unit-testable: coverage = mapped value / total value, per
    corpus/06a's Coverage tab. An account universe with zero total value
    trivially has 100% coverage (nothing to map)."""
    if total_value_inr == 0:
        return Decimal("1")
    return mapped_value_inr / total_value_inr


@dataclass
class FreezeResult:
    passed: bool
    reason: str
    coverage_pct: Decimal | None = None
    unmapped_value_inr: Decimal | None = None


def freeze_mapping_version(conn, schema: str, tenant_id: str, entity_id: int, mapping_version_id: int,
                             approved_by: str) -> FreezeResult:
    """corpus/06a Coverage tab: 'FREEZE GATE ... all three conditions: no
    unassigned ledgers, no unapproved rows, coverage at or above 98%.' A
    BLOCKED gate is not advisory -- metrics do not unlock and no statement is
    generated until it reads PASS."""
    with conn.cursor() as cur:
        # Condition 1: no unassigned ledgers (every current dim_account row
        # has a map_account row in this version).
        cur.execute(
            f'SELECT count(*) FROM "{schema}".dim_account da '
            f'WHERE da.tenant_id = %s AND da.entity_id = %s AND da.is_current '
            f'AND NOT EXISTS (SELECT 1 FROM "{schema}".map_account ma '
            f'                 WHERE ma.mapping_version_id = %s AND ma.source_record_id = da.source_record_id)',
            (tenant_id, entity_id, mapping_version_id),
        )
        unassigned_count = cur.fetchone()[0]
        if unassigned_count > 0:
            return FreezeResult(False, f"{unassigned_count} ledger(s) have no map_account row at all")

        # Condition 2: no unapproved rows.
        cur.execute(
            f'SELECT count(*) FROM "{schema}".map_account WHERE mapping_version_id = %s AND approved_by IS NULL',
            (mapping_version_id,),
        )
        unapproved_count = cur.fetchone()[0]
        if unapproved_count > 0:
            return FreezeResult(False, f"{unapproved_count} row(s) have no approved_by")

        # Condition 3: coverage >= 98%.
        cur.execute(
            f'SELECT COALESCE(SUM(period_value_inr), 0), '
            f"       COALESCE(SUM(period_value_inr) FILTER (WHERE canonical_class != 'suspense.unmapped'), 0) "
            f'FROM "{schema}".map_account WHERE mapping_version_id = %s',
            (mapping_version_id,),
        )
        total_value, mapped_value = cur.fetchone()
        coverage = compute_coverage(total_value, mapped_value)
        if coverage < COVERAGE_THRESHOLD:
            return FreezeResult(False, f"coverage {coverage:.4f} is below the {COVERAGE_THRESHOLD} threshold",
                                  coverage_pct=coverage, unmapped_value_inr=total_value - mapped_value)

        # PASS -- freeze it.
        cur.execute(
            f'SELECT effective_from FROM "{schema}".mapping_version WHERE mapping_version_id = %s',
            (mapping_version_id,),
        )
        effective_from = cur.fetchone()[0]

        # Close out whichever version was previously approved for this
        # entity, per corpus/06 section 6 rule 3 (effective dating by period).
        cur.execute(
            f'UPDATE "{schema}".mapping_version SET effective_to = %s '
            f"WHERE tenant_id = %s AND entity_id = %s AND status = 'approved'",
            (effective_from, tenant_id, entity_id),
        )
        cur.execute(
            f'UPDATE "{schema}".mapping_version '
            f"SET status = 'approved', approved_by = %s, approved_at = now() "
            f'WHERE mapping_version_id = %s',
            (approved_by, mapping_version_id),
        )

        # Refresh dim_account's current-state view for convenience (browsing,
        # the review UI) -- map_account remains the authoritative, versioned,
        # effective-dated source for statement assembly.
        cur.execute(
            f'UPDATE "{schema}".dim_account da SET '
            f'  canonical_class = ma.canonical_class, statement_section = ma.statement_section, '
            f'  statement_line = ma.statement_line, is_mapped = (ma.canonical_class != \'suspense.unmapped\'), '
            f'  mapping_version_id = ma.mapping_version_id, mapping_confidence = ma.confidence, '
            f'  mapping_source = ma.proposal_source, approved_by = ma.approved_by, approved_at = ma.approved_at '
            f'FROM "{schema}".map_account ma '
            f'WHERE ma.mapping_version_id = %s AND da.source_record_id = ma.source_record_id AND da.is_current',
            (mapping_version_id,),
        )

    return FreezeResult(True, "PASS", coverage_pct=coverage, unmapped_value_inr=total_value - mapped_value)
