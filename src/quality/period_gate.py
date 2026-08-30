"""Period reportability on the read paths, corpus/09 section 5.

src/quality/period_state.py owns the transitions -- which arrows exist and
what each one requires. This module owns the other half: what a period in a
given state is allowed to be *read* as. They are separate concerns and are
deliberately separate modules; nothing here writes a period_lock row.

corpus/09 section 5 annotates two of its states with what they unlock, and
those annotations are the gate:

    MAPPED       "metrics computable, statements assemble"
    RECONCILED   "pack may be generated"

So a statement, a metric or an operating view needs MAPPED or later, and a
management pack needs RECONCILED or later. Nothing here invents a threshold
(CLAUDE.md section 3.2) -- both sets are corpus/09's own sentences read
literally, and LOCKED is in both because section 5 draws it downstream of
each ("snapshot_at pinned. Reports render against this snapshot forever").

**RESTATED is in STATEMENTS_REPORTABLE and not in PACK_REPORTABLE.**
corpus/09 section 5 draws RESTATED as a terminal state -- "new period_lock
row, pointer to the prior one, delta explained" -- and says nothing about
whether a period in it may be read, so the split is a decision on record
rather than a sentence of the corpus (OPEN_QUESTIONS.md OQ-010, resolved
2026-08-31). It mirrors the MAPPED/RECONCILED split section 5 already
draws, for the same reason. Refusing a restated period on the statement
surfaces would hide the corrected number and leave the superseded one as
the last thing anybody saw, which is the worse of the two failures. A pack
is different: it is signed against a locked period (D-039) and RESTATED is
entered the moment a change *arrives*, before the delta has been explained,
so a pack generated from one would carry a signature over a number no human
has reviewed.

**The gate belongs at the route and service boundary, never inside
assemble_*.** The assembly functions in src/reports are the thing that
computes a statement from facts; whether a period may be shown at all is a
policy decision about a request, made once, where the request arrives. Eight
test files call the assembly functions directly to check the arithmetic, and
those tests are about the arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from src.quality.period_state import get_current_period_lock
from src.reports.query import NoApprovedMappingError, resolve_mapping_version_for_period
from src.semantic.citation import fetch_unmapped_value_inr

# corpus/09 section 5's own annotations, as data, plus OQ-010's resolution of
# where 'restated' sits. See this module's docstring for the reasoning on
# each set.
STATEMENTS_REPORTABLE: tuple[str, ...] = ("mapped", "reconciled", "locked", "restated")
PACK_REPORTABLE: tuple[str, ...] = ("reconciled", "locked")


class PeriodNotReportable(Exception):
    """Raised by a service that will not produce output for a period in its
    current state. Carries the reportability so a caller can render it as a
    422 detail or a corpus/07 section 6 refusal without re-querying."""

    def __init__(self, reportability: "PeriodReportability"):
        self.reportability = reportability
        super().__init__(reportability.detail())


@dataclass
class PeriodReportability:
    """One period's answer to "may this be read?", with everything a refusal
    needs already resolved.

    unmapped_value_inr is corpus/07 section 6's required second figure for
    the "period not reportable" class ("states the reconciliation status and
    the unmapped rupee value"). It is None exactly when it is not honestly
    computable -- see resolve_period_reportability."""

    period_key: str
    status: str
    required: tuple[str, ...]
    reportable: bool
    unmapped_value_inr: Decimal | None = None
    unmapped_value_unavailable_reason: str | None = None

    def detail(self) -> str:
        """The 422 body. Names the period's actual current status, which is
        the one thing the reader needs in order to know what to do next."""
        base = (
            f"{self.period_key} is not reportable: its period state is {self.status!r}, and corpus/09 "
            f"section 5 admits {' or '.join(self.required)} for this output."
        )
        if self.status == "restated":
            base += (
                " A restated period is readable on the statement surfaces and is not packable: a pack is"
                " signed against a locked period (D-039), and RESTATED is entered when a change arrives,"
                " before the delta has been explained."
            )
        return base


def months_in_range(period_start: date, period_end: date) -> list[str]:
    """Every 'YYYY-MM' period_key touched by an inclusive date range. The
    grain is one calendar month throughout this system (corpus/04's
    period_key), so a statement asked for 1 Jan to 15 Feb touches two."""
    if period_end < period_start:
        raise ValueError(f"period_end {period_end} precedes period_start {period_start}")
    keys, year, month = [], period_start.year, period_start.month
    while (year, month) <= (period_end.year, period_end.month):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return keys


def _unmapped_value(conn, schema: str, tenant_id: str, entity_id: int,
                       period_key: str) -> tuple[Decimal | None, str | None]:
    """corpus/07 section 6's unmapped rupee value for a period that is being
    refused -- resolved through the mapping version that actually governs the
    period (corpus/06 section 6 rule 3's effective dating), never through the
    version the period_lock row happens to point at.

    That distinction is the whole point. A VALIDATED period's lock row points
    at the ingestion-time placeholder (version_no = 0, db/migrations/tenant/
    0005), and the placeholder has no map_account rows at all -- so summing
    suspense.unmapped through it returns Rs 0. Reporting "unmapped value is
    Rs 0" while refusing the period *for being unmapped* would be a
    fabricated number in a refusal whose entire job is to state that figure
    honestly (CLAUDE.md section 3.4).

    When no approved mapping version covers the period there is no universe
    to measure unmapped value against, and the honest answer is that the
    figure does not exist yet -- returned as a stated reason, never as a
    zero.
    """
    year, month = (int(p) for p in period_key.split("-"))
    period_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    try:
        mapping_version_id = resolve_mapping_version_for_period(conn, schema, tenant_id, entity_id, period_end)
    except NoApprovedMappingError as e:
        return None, (
            f"no approved mapping version covers {period_key}, so no unmapped rupee value exists to "
            f"report yet ({e})"
        )
    return fetch_unmapped_value_inr(conn, schema, mapping_version_id), None


def resolve_period_reportability(conn, schema: str, tenant_id: str, entity_id: int, period_key: str,
                                    required: tuple[str, ...]) -> PeriodReportability:
    """Whether `period_key` may be read for an output requiring `required`.

    OPEN is the absence of a period_lock row, the same convention every
    other reader in this codebase uses (src/quality/period_state.py's own
    note on _PREDECESSOR).

    The unmapped rupee value is resolved only on the refusing path, since
    that is the only path corpus/07 section 6 requires it for -- a reportable
    period costs no extra query here.
    """
    lock = get_current_period_lock(conn, schema, tenant_id, entity_id, period_key)
    status = lock.status if lock is not None else "open"
    if status in required:
        return PeriodReportability(period_key, status, required, reportable=True)

    unmapped, unavailable_reason = _unmapped_value(conn, schema, tenant_id, entity_id, period_key)
    return PeriodReportability(period_key, status, required, reportable=False,
                                  unmapped_value_inr=unmapped,
                                  unmapped_value_unavailable_reason=unavailable_reason)


def first_unreportable(conn, schema: str, tenant_id: str, entity_id: int, period_keys: list[str],
                          required: tuple[str, ...]) -> PeriodReportability | None:
    """The first period in `period_keys` that may not be read, or None if
    every one of them may.

    Used by the statement and operating routes, whose requests span a date
    range. **Any unreportable month in the range refuses the whole request.**
    A P&L is one set of totals, not a per-month series: serving it while
    silently dropping or including a month nobody has mapped produces a
    single number that looks complete and is not, which is the failure mode
    this system exists to prevent (CLAUDE.md section 1). Ask's metric_trend
    is the deliberate contrast -- it returns a labelled value per month, so
    it reports each month's state in place rather than refusing the window.
    """
    for period_key in period_keys:
        reportability = resolve_period_reportability(conn, schema, tenant_id, entity_id, period_key, required)
        if not reportability.reportable:
            return reportability
    return None
