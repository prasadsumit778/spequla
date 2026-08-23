"""Refusal, corpus/07 section 6.

"The refusal path is a feature, not an error state... 100 percent of
unanswerable questions must be refused. A single fabricated answer blocks
release." Seven classes, each with a required response shape: name the
class, state the reason, and -- "every refusal names the nearest supported
question" -- offer something the user actually can ask.

Which class a given question falls into is a judgement a real system makes
by classifying against context (an unreconciled period, a genuinely-missing
data source, an undecided policy). Nothing here fabricates that judgement
for an arbitrary question -- REFUSAL_CLASSES is the fixed vocabulary
corpus/07 defines; build_refusal() just assembles the structured response
once the caller (a model's intent classification, or a deterministic check
like period reportability) has already determined which class applies.
"""
from __future__ import annotations

from dataclasses import dataclass

REFUSAL_CLASSES = (
    "out_of_scope",              # "What will revenue be next quarter?" -- forecasting is P1
    "requires_documents",         # "What does our supply contract say...?"
    "requires_data_not_held",      # "What is our CAC?" -- names the missing input
    "requires_decision_not_made",   # "What is our contribution margin?" before D-048
    "period_not_reportable",         # any metric for an unreconciled or unmapped period
    "genuinely_unanswerable",         # "Which of our competitors is growing fastest?"
    "ambiguous",                       # "How are we doing?"
)


@dataclass
class Refusal:
    refusal_class: str
    reason: str
    nearest_supported_question: str | None = None
    clarifying_options: list[str] | None = None

    def __post_init__(self):
        if self.refusal_class not in REFUSAL_CLASSES:
            raise ValueError(f"{self.refusal_class!r} is not one of corpus/07 section 6's seven refusal classes")


def build_refusal(refusal_class: str, reason: str, nearest_supported_question: str | None = None,
                     clarifying_options: list[str] | None = None) -> Refusal:
    return Refusal(refusal_class=refusal_class, reason=reason,
                     nearest_supported_question=nearest_supported_question, clarifying_options=clarifying_options)


def refusal_for_unreportable_period(period_key: str, period_status: str, unmapped_value_inr) -> Refusal:
    """corpus/07 section 6: 'Period not reportable | Any metric for an
    unreconciled or unmapped period | States the reconciliation status and
    the unmapped rupee value.'"""
    return build_refusal(
        "period_not_reportable",
        f"{period_key} is not reportable: status is {period_status!r}, unmapped value is "
        f"Rs {unmapped_value_inr}.",
        nearest_supported_question=f"Is {period_key} reconciled?",
    )


def refusal_for_blocked_decision(metric_id: str, blocking_decisions: list[str]) -> Refusal:
    """corpus/07 section 6: 'Requires a decision not made | ... | Names the
    decision and who must make it.'"""
    return build_refusal(
        "requires_decision_not_made",
        f"{metric_id!r} is blocked by {', '.join(blocking_decisions)} -- a company-specific accounting "
        f"policy decision that has not been made yet. It is resolved during the accounting policy "
        f"interview with your finance lead.",
        nearest_supported_question="Is this period reconciled?",
    )
