"""The mapping engine: extract, propose (exact rules only), auto-accept.

Implements corpus/06 section 4's six-step process, minus step 3 (AI
proposal) per your explicit sprint 2 scope:

    1. Extract COA               <- extract_coa()
    2. Apply exact rules         <- propose_mappings()
    3. Propose the remainder     -- NOT built this sprint
    4. Auto-accept the obvious   <- evaluate_auto_accept()
    5. Queue everything else     -- src/mapping/review.py
    6. Human approves, freeze    -- src/mapping/review.py

Everything an exact rule does not match is queued for review rather than
guessed, exactly as it would be if step 3 existed and also failed to propose
anything -- this sprint just never has a step 3 to fall back to.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from src.mapping.rules import Rule, extract_channel_geo, match_exact_rule


@dataclass
class AccountToMap:
    account_key: int
    source_record_id: str
    source_account_name: str
    source_parent_group: str | None
    period_value_inr: Decimal


@dataclass
class Proposal:
    account: AccountToMap
    canonical_class: str
    derived_channel: str | None
    derived_geo: str | None
    proposal_source: str  # 'exact_rule' -- the only source this sprint builds
    proposal_reason: str
    rule: Rule


def extract_coa(conn, schema: str, tenant_id: str, entity_id: int) -> list[AccountToMap]:
    """corpus/06 section 4 step 1. period_value_inr is the sum of absolute
    amount_base movement across every ingested fact for that account -- this
    sprint ingests a synthetic company's full history in one pass rather than
    incrementally month by month, so "twelve months of movement" (corpus/06
    section 4.1) collapses to "all movement seen so far"."""
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT da.account_key, da.source_record_id, da.source_account_name, da.source_parent_group, '
            f'       COALESCE(SUM(ABS(fg.amount_base)), 0) '
            f'FROM "{schema}".dim_account da '
            f'LEFT JOIN "{schema}".fact_gl_entry fg '
            f'  ON fg.account_key = da.account_key AND fg.tenant_id = da.tenant_id AND fg.is_current '
            f'WHERE da.tenant_id = %s AND da.entity_id = %s AND da.is_current '
            f'GROUP BY da.account_key, da.source_record_id, da.source_account_name, da.source_parent_group',
            (tenant_id, entity_id),
        )
        return [
            AccountToMap(account_key=r[0], source_record_id=r[1], source_account_name=r[2],
                          source_parent_group=r[3], period_value_inr=r[4])
            for r in cur.fetchall()
        ]


def propose_mappings(accounts: list[AccountToMap]) -> tuple[list[Proposal], list[AccountToMap]]:
    """corpus/06 section 4 step 2. Returns (proposed, unmatched). Unmatched
    accounts are not guessed at -- they are queued for review and, absent a
    human decision, default to suspense.unmapped per corpus/06 section 4.4."""
    proposed: list[Proposal] = []
    unmatched: list[AccountToMap] = []
    for account in accounts:
        rule = match_exact_rule(account.source_account_name)
        if rule is None:
            unmatched.append(account)
            continue
        channel, geo = extract_channel_geo(account.source_account_name)
        proposed.append(Proposal(
            account=account, canonical_class=rule.canonical_class,
            derived_channel=channel, derived_geo=geo,
            proposal_source="exact_rule",
            proposal_reason=f"Exact match against the rule library: {account.source_account_name!r} -> {rule.canonical_class}",
            rule=rule,
        ))
    return proposed, unmatched


def evaluate_auto_accept(
    proposal: Proposal,
    judgement_classes: set[str],
    prior_approved_class: str | None,
    rupee_ceiling: Decimal | None,
) -> tuple[bool, str]:
    """corpus/06 section 4.2. All four conditions must hold. rupee_ceiling is
    None because the corpus declares this gate ("the account's period value
    below a declared rupee ceiling") without stating the number -- see
    OPEN_QUESTIONS.md OQ-001. With rupee_ceiling=None this condition is
    skipped rather than defaulted to some invented number; every other
    condition still applies in full, so auto-accept is still refused outright
    for every judgement class regardless of ceiling status.

    Returns (accepted, reason) -- reason is always populated, including on
    acceptance, so the audit trail can say why."""
    if proposal.proposal_source != "exact_rule":
        return False, "not an exact-rule match"
    if proposal.canonical_class in judgement_classes:
        return False, f"{proposal.canonical_class} is a judgement class -- never auto-accepted"
    if prior_approved_class is not None and prior_approved_class != proposal.canonical_class:
        return False, (f"conflicts with a prior approved mapping ({prior_approved_class} -> "
                         f"{proposal.canonical_class})")
    if rupee_ceiling is not None and proposal.account.period_value_inr >= rupee_ceiling:
        return False, f"period value {proposal.account.period_value_inr} is at or above the declared ceiling"

    reason = "exact rule match, not a judgement class, no conflicting prior mapping"
    if rupee_ceiling is None:
        reason += " (rupee ceiling undeclared -- OQ-001 -- not gated on)"
    return True, reason
