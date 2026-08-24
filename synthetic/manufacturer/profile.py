"""The fictional manufacturer's accounting policy choices.

Per corpus/00, D-001, D-002, D-006, D-012, D-015, D-016, D-017 and D-018 were
resolved 2026-08-24 -- for the apparel pilot's own books, but enforced as
**global** defaults (src/config/loader.py's ConfigRegistry reads one
config/decisions.yml, not one per tenant; there is no per-tenant override
mechanism built yet, despite corpus/00 section 1 rule 2's framing of one as
always available). This company's own GL and mapping rules
(synthetic/manufacturer/engine.py, src/mapping/rules.py) already matched
several of these by construction before the resolution (GST exclusive,
invoice-date revenue, freight inward expensed); D-015/D-016 specifically
changed the ENFORCED classification under this company (power/fuel and
direct labour now map to opex.power_fuel/opex.direct_labour, not
cogs.power_fuel/cogs.direct_labour) even though nothing in this generator's
own mechanics needed to change -- only the taxonomy and mapping rules did.
D-041 and D-042 remain genuinely open (still per-company, still unresolved).

  D-001 GST treatment              -> exclusive (sales ledgers booked net of GST) -- global default
  D-002 revenue recognition point  -> invoice date -- global default
  D-012 freight inward             -> expensed (not capitalised into inventory) -- global default
  D-015 power and fuel             -> opex, not COGS -- global default (was COGS via absorption
                                       in this company's own conceptual model; corpus/00 overrides)
  D-016 direct labour              -> opex, not COGS -- global default (this company's own
                                       cost-centre split DOES exist, unlike corpus/06's general note)
  D-017 costing basis              -> standard costing, variance in COGS -- global default,
                                       matches this company's own policy (so defect #13, absorption
                                       variance masking a margin fall, has somewhere to hide)
  D-018 inventory valuation        -> global default is FIFO; THIS company's own books use
                                       weighted average -- a real mismatch, tracked here rather
                                       than silently resolved, until a per-tenant override exists
  D-041 declared unit of measure   -> MT (metric tonnes) per product family -- still open, this
                                       company's own answer only, not enforced anywhere
  D-042 capacity basis             -> practical capacity -- still open, this company's own answer only
"""
from datetime import date
from decimal import Decimal

COMPANY_NAME = "SYNTHETIC Ferrotech Industries Pvt Ltd"
GST_RATE = Decimal("0.18")
FISCAL_START = date(2023, 4, 1)  # FY24 April
N_MONTHS = 36                     # through March 2026 (FY24, FY25, FY26)
ANNUAL_REVENUE_Y1 = Decimal("1000000000")  # ~INR 100 Cr in year 1
YOY_GROWTH = Decimal("0.08")
GROSS_MARGIN_TARGET = Decimal("0.30")
OPEX_PCT_OF_REVENUE = Decimal("0.15")
