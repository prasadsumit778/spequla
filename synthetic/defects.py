"""The thirteen deliberate defects in the synthetic manufacturer dataset.

Implements corpus/11_SPEQULA_EVALUATION_FRAMEWORK.md section 2.2 verbatim,
each mapped to the corpus/09 check it is meant to trigger, per your Sprint 0
instruction ("Seed all thirteen defects listed in /corpus/11 section 2.2").
This module is documentation plus a shared registry other generator modules
import from, so where a defect landed is never duplicated or drifted between
the generator code and this list.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Defect:
    id: int
    description: str  # verbatim from corpus/11 section 2.2
    check: str        # the corpus/09 check it is meant to trigger
    lands_in: str      # which template/file the defect is injected into


DEFECTS: list[Defect] = [
    Defect(1, "A backdated journal batch posted into a prior, already-locked month",
           "Bitemporality, restatement path (corpus/09 section 2.6)", "GL"),
    Defect(2, "A duplicate voucher run, same content, different ids",
           "Deduplication on row_hash (corpus/09 section 2.3)", "GL"),
    Defect(3, "One month where the bank file is missing entirely",
           "Completeness, BLOCKING (corpus/09 section 2.1)", "Bank"),
    Defect(4, "A trial balance that fails to balance in exactly one month",
           "Trial balance zero-tolerance BLOCKING check, D-051 (corpus/09 section 2.4/3.1)", "GL / TB"),
    Defect(5, "A ledger that appears mid-year carrying large value",
           "Continuity check, value-sorted queue (corpus/09 section 2.6)", "GL / COA"),
    Defect(6, "A source file whose column headers change between two months",
           "Schema hash BLOCKING (corpus/09 section 2.6)", "GL export"),
    Defect(7, "A product family with two units of measure",
           "D-041 constraint -- blocks rather than converts (corpus/09 section 2.2)", "MFG Production"),
    Defect(8, "A credit note with no reason code",
           "Returns-vs-discount classification exception (corpus/09 section 2.1/2.2)", "Sales Register"),
    Defect(9, "A margin sign flip on one product in one month",
           "Anomaly surfaced as exception, never as insight (corpus/09 section 2.7)", "Sales Register"),
    Defect(10, "Twelve ledgers that fit no canonical class cleanly",
           "Suspense handling (corpus/06 section 3.6)", "COA"),
    Defect(11, "A #DIV/0! cell in an uploaded spreadsheet",
           "Validity check must quarantine rather than coerce to zero (corpus/09 section 2.2)", "Sales Register"),
    Defect(12, "A consumer line with revenue and zero COGS",
           "100 percent gross margin must not raise an anomaly (corpus/09 section 2.7)", "Consumer Sales"),
    Defect(13, "A month where absorption variance masks a real margin fall",
           "The D-017 manufacturing trap (corpus/03 section 2.2)", "GL (manufacturing)"),
]

assert len(DEFECTS) == 13, "corpus/11 section 2.2 lists thirteen defects; keep this list in sync"
