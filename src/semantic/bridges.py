"""Deterministic decomposition bridges for variance_explain, corpus/07
section 5.

    1. Compute the metric for both periods.            DET
    2. Compute the delta.                               DET
    3. Run the applicable bridge.                        DET
    4. Check the components sum to the total delta.       DET  <- the gate
    5. Rank components by absolute contribution.            DET
    6. Narrate, receiving the computed numbers.               AI

Step 4 is a genuine gate here, not a formality: every bridge below is built
so its components are an EXACT algebraic identity of the total (the last
component is always constructed as whatever is left over, per D-059's own
resolved convention -- "mix as residual. Residual always reported"),
so a real mismatch means something upstream is wrong, not that a rounding
tolerance needs to be invented. CLAUDE.md 3.2 already governs this: no
threshold is fabricated where the corpus is silent, and Decimal arithmetic
(never float, per CLAUDE.md section 8) does not accumulate rounding error
the way a naive percentage decomposition might.

corpus/07 section 5 names three bridges. Only the revenue bridge has a
worked formula anywhere in the corpus (D-059). The margin bridge is named
("input cost, price, mix, other") with no worked allocation given -- per
CLAUDE.md 3.1, this module does not invent one. compute_margin_bridge
returns a NotConfigured result rather than a number, exactly matching
section 5's own stated fallback: "the system reports the total movement and
the components it can compute unambiguously, and states that the
decomposition is unavailable rather than silently choosing a convention."
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class BridgeComponent:
    label: str
    value: Decimal
    is_residual: bool = False


@dataclass
class BridgeResult:
    total_delta: Decimal
    components: list[BridgeComponent] = field(default_factory=list)
    components_sum_to_total: bool = True
    configured: bool = True
    reason: str | None = None

    def ranked(self) -> list[BridgeComponent]:
        """corpus/07 section 5 step 5: rank by absolute contribution."""
        return sorted(self.components, key=lambda c: abs(c.value), reverse=True)


def not_configured(total_delta: Decimal, reason: str) -> BridgeResult:
    return BridgeResult(total_delta=total_delta, components=[], components_sum_to_total=False,
                          configured=False, reason=reason)


def compute_revenue_bridge(prior_price: Decimal, prior_volume: Decimal,
                              current_price: Decimal, current_volume: Decimal) -> BridgeResult:
    """D-059's resolved convention (corpus/00 section 2b): 'Volume at
    prior-period price, price at current-period volume, mix as residual.
    Residual always reported.'

        volume_effect = (current_volume - prior_volume) * prior_price
        price_effect  = (current_price - prior_price) * current_volume
        mix           = total_delta - volume_effect - price_effect   (residual, by construction)
    """
    total_delta = (current_price * current_volume) - (prior_price * prior_volume)
    volume_effect = (current_volume - prior_volume) * prior_price
    price_effect = (current_price - prior_price) * current_volume
    mix = total_delta - volume_effect - price_effect

    components = [
        BridgeComponent("volume", volume_effect),
        BridgeComponent("price", price_effect),
        BridgeComponent("mix", mix, is_residual=True),
    ]
    check_total = sum((c.value for c in components), Decimal("0"))
    return BridgeResult(total_delta=total_delta, components=components,
                          components_sum_to_total=(check_total == total_delta))


def compute_ebitda_bridge(gross_profit_delta: Decimal, opex_line_deltas: dict[str, Decimal],
                             ebitda_delta: Decimal) -> BridgeResult:
    """corpus/07 section 5: 'ebitda -> gross profit change, opex lines.'
    ebitda = gross_profit - opex_total, so ebitda_delta = gross_profit_delta
    - sum(opex_line_deltas) exactly, provided opex_line_deltas covers every
    opex line (it is the metric registry's own opex_total broken into its
    canonical-class lines, not a hand-picked subset) -- an exact identity,
    not an estimate. ebitda_delta is passed in (already independently
    computed by the caller from compile_metric) rather than re-derived here,
    so step 4's check is a genuine cross-check against a real second
    computation, not the bridge checking itself."""
    components = [BridgeComponent("gross_profit", gross_profit_delta)]
    components.extend(BridgeComponent(f"opex:{label}", -delta) for label, delta in opex_line_deltas.items())
    check_total = sum((c.value for c in components), Decimal("0"))
    return BridgeResult(total_delta=ebitda_delta, components=components,
                          components_sum_to_total=(check_total == ebitda_delta))


def compute_margin_bridge(*args, **kwargs) -> BridgeResult:
    """Not implemented -- corpus/07 section 5 names this bridge ('margin ->
    input cost, price, mix, other') but no worked allocation formula exists
    anywhere in the corpus, unlike the revenue bridge's D-059. Inventing one
    would be inventing a financial definition (CLAUDE.md 3.1). Returns the
    same 'not yet configured' outcome corpus/07 section 5 itself specifies
    for an undeclared convention."""
    return not_configured(Decimal("0"), "the margin bridge's price/cost/mix allocation is not "
                                            "declared anywhere in the corpus -- see OPEN_QUESTIONS.md")


def compute_cash_bridge(operating_cf: Decimal, investing_cf: Decimal, financing_cf: Decimal,
                           total_cash_delta: Decimal) -> BridgeResult:
    """Standard indirect-method identity: opening cash + operating +
    investing + financing = closing cash, so their sum must equal the total
    cash movement exactly (corpus/03 section 4, corpus/08 section 6)."""
    components = [
        BridgeComponent("operating", operating_cf),
        BridgeComponent("investing", investing_cf),
        BridgeComponent("financing", financing_cf),
    ]
    check_total = sum((c.value for c in components), Decimal("0"))
    return BridgeResult(total_delta=total_cash_delta, components=components,
                          components_sum_to_total=(check_total == total_cash_delta))
